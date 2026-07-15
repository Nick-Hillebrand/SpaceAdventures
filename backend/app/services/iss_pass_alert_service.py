"""ISS visual pass alert precompute + notify worker jobs
(Architecture/20-location-and-sky-alerts.md L1).

- `precompute_passes` is the `pass_precompute` job body (every 6 h): for each
  Pro user with a saved location AND an active `iss_pass` subscription, fetch
  N2YO visual passes for the next 2 days. Users sharing the same rounded
  (lat, lng) are batched into ONE N2YO call — this is what keeps the 1000/hr
  quota viable at thousands of users.
- `notify_passes` is the `pass_notify` job body (every 5 min): claims
  not-yet-notified passes starting 25-35 min from now with max elevation
  >= 25 degrees, atomically (so two concurrent runs never double-enqueue),
  and enqueues an outbox notification for each.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.iss_pass_alert import IssPassAlert
from app.models.notification_log import PendingNotification
from app.models.subscription import Subscription
from app.models.user import User
from app.services.iss_service import _check_and_increment_quota
from app.services.n2yo_client import N2YOClient, N2YOError, _QUOTA_LOCK

PASS_PRECOMPUTE_DAYS = 2
PASS_PRECOMPUTE_MIN_VISIBILITY = 120  # seconds

NOTIFY_WINDOW_START_MINUTES = 25
NOTIFY_WINDOW_END_MINUTES = 35
NOTIFY_MIN_ELEVATION_DEGREES = 25.0


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


async def _eligible_locations(session: AsyncSession) -> dict[tuple[float, float], list[User]]:
    """Pro users with a saved location and an active `iss_pass` subscription,
    grouped by their (already-rounded) (lat, lng) coordinate."""
    stmt = select(User).join(Subscription, Subscription.user_id == User.id).where(
        User.is_pro.is_(True),
        User.location_lat.is_not(None),
        User.location_lng.is_not(None),
        Subscription.type == "iss_pass",
    )
    result = await session.execute(stmt)
    groups: dict[tuple[float, float], list[User]] = {}
    for user in result.scalars().all():
        key = (user.location_lat, user.location_lng)
        groups.setdefault(key, []).append(user)
    return groups


def _safe_float(value: object) -> float | None:
    """Rule 9: upstream data is untrusted — parse defensively, never trust shape."""
    if value is None:
        return None
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _parse_pass(raw: dict) -> dict | None:
    """Validate one N2YO visualpasses entry; return None to skip a malformed row
    (rule 9) rather than storing partial/garbage data."""
    try:
        start_utc = datetime.fromtimestamp(int(raw["startUTC"]), tz=timezone.utc)
        end_utc = datetime.fromtimestamp(int(raw["endUTC"]), tz=timezone.utc)
        max_el = float(raw["maxEl"])
        start_az = float(raw["startAz"])
        end_az = float(raw["endAz"])
    except (KeyError, TypeError, ValueError):
        return None
    return {
        "start_utc": start_utc,
        "end_utc": end_utc,
        "max_el": max_el,
        "start_az": start_az,
        "end_az": end_az,
        "mag": _safe_float(raw.get("mag")),
    }


async def _upsert_pass(session: AsyncSession, user_id: int, parsed: dict) -> None:
    result = await session.execute(
        select(IssPassAlert).where(
            IssPassAlert.user_id == user_id, IssPassAlert.start_utc == parsed["start_utc"]
        )
    )
    existing = result.scalar_one_or_none()
    if existing is None:
        session.add(IssPassAlert(user_id=user_id, fetched_at=_utcnow(), **parsed))
        return
    existing.end_utc = parsed["end_utc"]
    existing.max_el = parsed["max_el"]
    existing.start_az = parsed["start_az"]
    existing.end_az = parsed["end_az"]
    existing.mag = parsed["mag"]
    existing.fetched_at = _utcnow()


async def precompute_passes(session: AsyncSession, client: N2YOClient, cap: int) -> None:
    groups = await _eligible_locations(session)
    for (lat, lng), users in groups.items():
        async with _QUOTA_LOCK:
            _quota, exceeded = await _check_and_increment_quota(session, cap)
            if exceeded:
                return  # never busy-wait — resume on the next scheduled run
            try:
                data = await client.get_visual_passes(
                    lat,
                    lng,
                    0.0,
                    days=PASS_PRECOMPUTE_DAYS,
                    min_visibility=PASS_PRECOMPUTE_MIN_VISIBILITY,
                )
            except N2YOError:
                continue  # this batch failed — move on to the next coordinate

        raw_passes = data.get("passes") or []
        parsed_passes = [p for p in (_parse_pass(entry) for entry in raw_passes) if p is not None]
        for user in users:
            for parsed in parsed_passes:
                await _upsert_pass(session, user.id, parsed)
        await session.commit()


async def _enqueue_notification(session: AsyncSession, alert: IssPassAlert) -> None:
    result = await session.execute(
        select(Subscription).where(
            Subscription.user_id == alert.user_id, Subscription.type == "iss_pass"
        )
    )
    subscription = result.scalar_one_or_none()
    if subscription is None:
        return  # user unsubscribed since precompute — nothing to notify
    session.add(
        PendingNotification(
            subscription_id=subscription.id,
            iss_pass_alert_id=alert.id,
            change_type="ISS_PASS",
        )
    )


async def notify_passes(session: AsyncSession) -> None:
    now = _utcnow()
    window_start = now + timedelta(minutes=NOTIFY_WINDOW_START_MINUTES)
    window_end = now + timedelta(minutes=NOTIFY_WINDOW_END_MINUTES)

    result = await session.execute(
        select(IssPassAlert).where(
            IssPassAlert.notified.is_(False),
            IssPassAlert.start_utc >= window_start,
            IssPassAlert.start_utc <= window_end,
            IssPassAlert.max_el >= NOTIFY_MIN_ELEVATION_DEGREES,
        )
    )
    alerts = list(result.scalars().all())

    for alert in alerts:
        # CONCURRENCY: this UPDATE's row lock (held until commit) is what
        # actually serializes concurrent pass_notify runs under Postgres
        # READ COMMITTED — the WHERE ... AND notified = False clause both
        # checks and claims the row in one atomic statement, so a rowcount
        # of 0 means a concurrent run already claimed it first.
        claim = await session.execute(
            update(IssPassAlert)
            .where(IssPassAlert.id == alert.id, IssPassAlert.notified.is_(False))
            .values(notified=True)
        )
        if claim.rowcount == 0:
            continue
        await _enqueue_notification(session, alert)
        await session.commit()
