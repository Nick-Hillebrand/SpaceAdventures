"""Business logic for Launch Library 2 launch syncing and retrieval."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone

from dateutil.parser import isoparse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.models.launches import Launch
from app.models.notification_log import PendingNotification
from app.models.subscription import Subscription
from app.services.ll2_client import LL2Client, LL2ClientError

logger = logging.getLogger(__name__)

_NET_SLIP_THRESHOLD_SECONDS = 5 * 60  # 5 minutes


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
    # Store as naive UTC
    if net_dt.tzinfo is not None:
        net_dt = net_dt.astimezone(timezone.utc).replace(tzinfo=None)

    livestream_urls = [
        {
            "title": v.get("title") or "",
            "url": v.get("url") or "",
            "feature_image": v.get("feature_image") or "",
        }
        for v in vidurls
        if v.get("url")
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
        "image_url": _trunc(_extract_image_url(raw.get("image")), 500),
        "livestream_urls": json.dumps(livestream_urls),
    }


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


async def sync_launches(session: AsyncSession, client: LL2Client, settings: Settings | None = None) -> None:
    """Fetch upcoming launches from LL2 and upsert into the DB."""
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

    fetched_at = datetime.now(timezone.utc).replace(tzinfo=None)
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

            # Update all fields
            for key, value in fields.items():
                setattr(existing, key, value)
            existing.fetched_at = fetched_at

    # Mark launches no longer returned as "Gone"
    if seen_ids:
        stmt = select(Launch).where(
            Launch.ll2_id.not_in(seen_ids),
            Launch.status_abbrev != "Gone",
        )
        result = await session.execute(stmt)
        for gone_launch in result.scalars().all():
            gone_launch.status_abbrev = "Gone"
    else:
        # If nothing was returned, mark everything Gone
        stmt = select(Launch).where(Launch.status_abbrev != "Gone")
        result = await session.execute(stmt)
        for gone_launch in result.scalars().all():
            gone_launch.status_abbrev = "Gone"

    await session.commit()

    # Drain notification queue if settings provided
    if settings is not None:
        from app.services import notification_service  # noqa: PLC0415
        await notification_service.drain_queue(session, settings)


async def get_upcoming_launches(
    session: AsyncSession,
) -> tuple[list[Launch], datetime | None]:
    """Return launches with net > now-24h, ordered by net asc.

    Also returns last_synced_at = MAX(fetched_at) or None.
    """
    cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=24)
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
