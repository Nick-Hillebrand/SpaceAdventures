"""Business logic for Launch Library 2 launch syncing and retrieval."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Awaitable, Callable

from dateutil.parser import isoparse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.launch_net_changes import LaunchNetChange
from app.models.launches import Launch
from app.models.notification_log import PendingNotification
from app.models.subscription import Subscription
from app.services.ll2_client import LL2Client, LL2ClientError
from app.services.notification_service import sanitise
from app.services.url_utils import sanitise_url

logger = logging.getLogger(__name__)

_NET_SLIP_THRESHOLD_SECONDS = 5 * 60  # 5 minutes

_Translator = Callable[[dict[str, str]], Awaitable[dict[str, dict[str, str]]]] | None


def _record_change(
    session: AsyncSession,
    launch_id: str,
    change_type: str,
    provider_name: str,
    rocket_name: str,
    pad_name: str | None,
    old_value: str | None = None,
    new_value: str | None = None,
) -> None:
    """Append one row to launch_net_changes in the caller's transaction.

    All string values from LL2 are sanitised before storage (10-security.md).
    This function is synchronous — session.add() does not require await.
    """
    session.add(
        LaunchNetChange(
            launch_id=launch_id,
            change_type=change_type,
            old_value=sanitise(old_value) if old_value is not None else None,
            new_value=sanitise(new_value) if new_value is not None else None,
            provider_name=sanitise(provider_name),
            rocket_name=sanitise(rocket_name),
            pad_name=sanitise(pad_name) if pad_name is not None else None,
        )
    )


def _trunc(value: object, max_len: int) -> str | None:
    if value is None or not isinstance(value, str):
        return None
    return value[:max_len]


def _trunc_required(value: object, max_len: int) -> str:
    if not isinstance(value, str):
        value = str(value) if value is not None else ""
    return value[:max_len]


def _extract_image_url(raw_image: object) -> str | None:
    """Handle LL2 API v2.3.0+ where 'image' changed from a URL string to an object."""
    if isinstance(raw_image, dict):
        return raw_image.get("image_url") or raw_image.get("thumbnail_url") or None
    if isinstance(raw_image, str):
        return raw_image or None
    return None


def _parse_raw(raw: dict) -> dict:
    """Extract and normalise fields from a raw LL2 launch dict."""
    vidurls = raw.get("vidURLs") or []
    mission = raw.get("mission") or {}
    status = raw.get("status") or {}
    rocket = raw.get("rocket") or {}
    config = rocket.get("configuration") or {}
    agency = raw.get("launch_service_provider") or {}
    pad = raw.get("pad") or {}
    location = pad.get("location") or {}

    # Parse net with isoparse to handle Z-suffix (Python < 3.11 fromisoformat limitation)
    raw_net = raw.get("net") or ""
    net_dt = isoparse(raw_net)
    if net_dt.tzinfo is not None:
        net_dt = net_dt.astimezone(timezone.utc)
    else:
        net_dt = net_dt.replace(tzinfo=timezone.utc)

    livestream_urls = [
        {
            "title": v.get("title") or "",
            "url": sanitise_url(v.get("url")) or "",
            "feature_image": sanitise_url(v.get("feature_image")) or "",
        }
        for v in vidurls
        if sanitise_url(v.get("url"))
    ]

    return {
        "ll2_id": raw.get("id") or "",
        "name": _trunc_required(raw.get("name") or "", 200),
        "net": net_dt,
        "status_abbrev": _trunc_required(status.get("abbrev") or "", 500),
        "status_name": _trunc_required(status.get("name") or "", 500),
        "agency_name": _trunc_required(agency.get("name") or "", 500),
        "agency_type": _trunc(agency.get("type"), 500),
        "rocket_name": _trunc_required(config.get("name") or "", 500),
        "rocket_family": _trunc(config.get("family"), 500),
        "mission_name": _trunc(mission.get("name"), 500),
        "mission_description": _trunc(mission.get("description"), 2000),
        "mission_type": _trunc(mission.get("type"), 500),
        "pad_name": _trunc_required(pad.get("name") or "", 500),
        "pad_location": _trunc_required(location.get("name") or "", 500),
        "image_url": _trunc(sanitise_url(_extract_image_url(raw.get("image"))), 500),
        "livestream_urls": livestream_urls,
    }


def _translation_fields(launch: Launch) -> dict[str, str]:
    """Collect the translatable text fields from a Launch row."""
    fields: dict[str, str] = {}
    if launch.mission_name:
        fields["mission_name"] = launch.mission_name
    if launch.mission_description:
        fields["mission_description"] = launch.mission_description
    return fields


async def _translate_launch(launch: Launch, translator: Any) -> None:
    """Translate mission fields and update launch.translations_json in-place."""
    fields = _translation_fields(launch)
    if not fields:
        return
    try:
        i18n = await translator(fields)
        launch.translations_json = i18n
    except Exception as exc:  # noqa: BLE001
        logger.warning("Launch translation for %s failed: %s", launch.ll2_id, exc)


async def _get_subscriptions_for_launch(
    session: AsyncSession, ll2_id: str, agency_name: str, change_type: str
) -> list[Subscription]:
    """Return subscriptions matching a launch-specific or agency-level subscription."""
    if change_type == "NEW_LAUNCH":
        # Only notify agency subscribers for brand-new launches
        stmt = select(Subscription).where(
            Subscription.type == "agency",
            Subscription.agency_name == agency_name,
        )
    else:
        # NET_SLIP and STATUS_CHANGE notify launch-specific and agency subscribers
        stmt = select(Subscription).where(
            (
                (Subscription.type == "launch") & (Subscription.ll2_id == ll2_id)
            )
            | (
                (Subscription.type == "agency") & (Subscription.agency_name == agency_name)
            )
        )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def _insert_pending_notifications(
    session: AsyncSession,
    ll2_id: str,
    agency_name: str,
    change_type: str,
    old_value: str | None = None,
    new_value: str | None = None,
) -> None:
    """Insert PendingNotification rows for all matching subscriptions."""
    subscriptions = await _get_subscriptions_for_launch(
        session, ll2_id, agency_name, change_type
    )
    for sub in subscriptions:
        notification = PendingNotification(
            subscription_id=sub.id,
            ll2_id=ll2_id,
            change_type=change_type,
            old_value=old_value,
            new_value=new_value,
        )
        session.add(notification)


async def sync_launches(
    session: AsyncSession,
    client: LL2Client,
    translator: _Translator = None,
) -> None:
    """Fetch upcoming launches from LL2 and upsert into the DB.

    Only enqueues `PendingNotification` rows — delivery is drained by the
    dedicated `notification_drain` job (17-worker-and-scheduling.md P3.2),
    never inline here, so a Twilio/SMTP outage can never delay a sync.
    """
    try:
        raw_launches = await client.fetch_upcoming()
    except LL2ClientError as exc:
        logger.error("LL2 sync failed: %s — %s", exc.code, exc.message)
        return

    if len(raw_launches) > 100:
        logger.warning(
            "LL2 returned %d launches; truncating to 100", len(raw_launches)
        )
        raw_launches = raw_launches[:100]

    fetched_at = datetime.now(timezone.utc)
    seen_ids: set[str] = set()

    for raw in raw_launches:
        try:
            fields = _parse_raw(raw)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to parse launch %s: %s", raw.get("id"), exc)
            continue

        ll2_id = fields["ll2_id"]
        if not ll2_id:
            continue
        seen_ids.add(ll2_id)

        # Load existing row
        existing: Launch | None = await session.get(Launch, ll2_id)

        if existing is None:
            # Brand new — insert NEW_LAUNCH notification for agency subscribers
            await _insert_pending_notifications(
                session,
                ll2_id=ll2_id,
                agency_name=fields["agency_name"],
                change_type="NEW_LAUNCH",
            )
            launch = Launch(fetched_at=fetched_at, **fields)
            session.add(launch)
            if translator is not None:
                await _translate_launch(launch, translator)
        else:
            # Check for NET_SLIP
            old_net: datetime = existing.net
            new_net: datetime = fields["net"]
            net_diff = abs((new_net - old_net).total_seconds())
            if net_diff > _NET_SLIP_THRESHOLD_SECONDS:
                await _insert_pending_notifications(
                    session,
                    ll2_id=ll2_id,
                    agency_name=fields["agency_name"],
                    change_type="NET_SLIP",
                    old_value=old_net.isoformat(),
                    new_value=new_net.isoformat(),
                )
                _record_change(
                    session,
                    launch_id=ll2_id,
                    change_type="net",
                    provider_name=fields["agency_name"],
                    rocket_name=fields["rocket_name"],
                    pad_name=fields["pad_name"],
                    old_value=old_net.isoformat(),
                    new_value=new_net.isoformat(),
                )

            # Check for STATUS_CHANGE
            if existing.status_abbrev != fields["status_abbrev"]:
                await _insert_pending_notifications(
                    session,
                    ll2_id=ll2_id,
                    agency_name=fields["agency_name"],
                    change_type="STATUS_CHANGE",
                    old_value=existing.status_abbrev,
                    new_value=fields["status_abbrev"],
                )
                _record_change(
                    session,
                    launch_id=ll2_id,
                    change_type="status",
                    provider_name=fields["agency_name"],
                    rocket_name=fields["rocket_name"],
                    pad_name=fields["pad_name"],
                    old_value=existing.status_abbrev,
                    new_value=fields["status_abbrev"],
                )

            # Re-translate if mission content changed or translations are missing
            needs_translation = translator is not None and (
                existing.translations_json is None
                or existing.mission_description != fields.get("mission_description")
                or existing.mission_name != fields.get("mission_name")
            )

            # Update all fields
            for key, value in fields.items():
                setattr(existing, key, value)
            existing.fetched_at = fetched_at

            if needs_translation:
                await _translate_launch(existing, translator)

    # Mark launches no longer returned as "Gone"
    if seen_ids:
        stmt = select(Launch).where(
            Launch.ll2_id.not_in(seen_ids),
            Launch.status_abbrev != "Gone",
        )
        result = await session.execute(stmt)
        for gone_launch in result.scalars().all():
            gone_launch.status_abbrev = "Gone"
            _record_change(
                session,
                launch_id=gone_launch.ll2_id,
                change_type="gone",
                provider_name=gone_launch.agency_name,
                rocket_name=gone_launch.rocket_name,
                pad_name=gone_launch.pad_name,
            )
    else:
        # If nothing was returned, mark everything Gone
        stmt = select(Launch).where(Launch.status_abbrev != "Gone")
        result = await session.execute(stmt)
        for gone_launch in result.scalars().all():
            gone_launch.status_abbrev = "Gone"
            _record_change(
                session,
                launch_id=gone_launch.ll2_id,
                change_type="gone",
                provider_name=gone_launch.agency_name,
                rocket_name=gone_launch.rocket_name,
                pad_name=gone_launch.pad_name,
            )

    await session.commit()


async def get_upcoming_launches(
    session: AsyncSession,
) -> tuple[list[Launch], datetime | None]:
    """Return launches with net > now-24h, ordered by net asc.

    Also returns last_synced_at = MAX(fetched_at) or None.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    stmt = (
        select(Launch)
        .where(Launch.net > cutoff)
        .order_by(Launch.net.asc())
    )
    result = await session.execute(stmt)
    launches = list(result.scalars().all())

    last_synced_stmt = select(func.max(Launch.fetched_at))
    last_synced_result = await session.execute(last_synced_stmt)
    last_synced_at: datetime | None = last_synced_result.scalar_one_or_none()

    return launches, last_synced_at


async def is_launches_table_empty(session: AsyncSession) -> bool:
    """Return True if the launches table has no rows."""
    stmt = select(func.count()).select_from(Launch)
    result = await session.execute(stmt)
    count: int = result.scalar_one()
    return count == 0


async def get_launch_by_id(session: AsyncSession, ll2_id: str) -> Launch | None:
    """Read a single launch by LL2 id — never triggers an upstream fetch."""
    return await session.get(Launch, ll2_id)


async def get_launch_history(
    session: AsyncSession, ll2_id: str, limit: int = 10
) -> list[LaunchNetChange]:
    """Most recent slip/status/gone changes for one launch, newest first."""
    stmt = (
        select(LaunchNetChange)
        .where(LaunchNetChange.launch_id == ll2_id)
        .order_by(LaunchNetChange.detected_at.desc())
        .limit(limit)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_next_launch(
    session: AsyncSession, provider: str | None = None
) -> "Launch | None":
    """Return the next upcoming non-Gone launch, optionally filtered by provider.

    Used by the embeddable widget (23-seo-widgets-and-growth.md L3).
    Provider filter is a case-insensitive substring match on agency_name.
    """
    cutoff = datetime.now(timezone.utc)
    stmt = (
        select(Launch)
        .where(Launch.net > cutoff, Launch.status_abbrev != "Gone")
    )
    if provider:
        stmt = stmt.where(Launch.agency_name.ilike(f"%{provider}%"))
    stmt = stmt.order_by(Launch.net.asc()).limit(1)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def get_sitemap_launches(session: AsyncSession) -> list[Launch]:
    """All upcoming + past-90-day launches (23-…md B2 sitemap) — excludes
    launches LL2 has stopped returning (status "Gone"), since those no
    longer have a meaningful public detail page."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=90)
    stmt = (
        select(Launch)
        .where(Launch.net > cutoff, Launch.status_abbrev != "Gone")
        .order_by(Launch.net.asc())
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())
