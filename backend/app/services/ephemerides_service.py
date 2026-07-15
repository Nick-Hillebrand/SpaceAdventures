"""Ephemeris cache service (Architecture/22-ephemeris-and-mission-replay.md
— Foundation).

Two responsibilities that must stay separate per the courtesy rules (NEVER
proxy a user request to JPL):

- ``get_ephemerides`` — read-only, serves the public API from the
  ``ephemerides`` table. Never calls Horizons.
- ``sync_tracked_object`` / ``run_ephemeris_sync`` — the `ephemeris_sync`
  worker job body. The only caller of ``HorizonsClient``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ephemerides import Ephemeris, TrackedObject
from app.services.horizons_client import HorizonsClient

MAX_RANGE_DAYS = 90

# Foundation coverage window: worker keeps every active object filled over
# [now-7d, now+30d]; trajectories are physics, so a covered instant is never
# re-fetched.
COVERAGE_PAST_DAYS = 7
COVERAGE_FUTURE_DAYS = 30


class UnknownSlugError(Exception):
    """Raised by `get_ephemerides` when no tracked object matches `slug`."""


def _validate_range(start: datetime, end: datetime) -> None:
    if end < start:
        raise ValueError("to must be on or after from")
    if (end - start).days > MAX_RANGE_DAYS:
        raise ValueError(f"range must be at most {MAX_RANGE_DAYS} days")


@dataclass
class EphemeridesResult:
    slug: str
    name_key: str
    points: list[Ephemeris]


async def get_ephemerides(
    session: AsyncSession, slug: str, start: datetime, end: datetime
) -> EphemeridesResult:
    """Read cached ephemerides for `slug` over `[start, end]`.

    Raises ``ValueError`` on an invalid range and ``UnknownSlugError`` if no
    tracked object has this slug. Never calls Horizons.
    """
    _validate_range(start, end)

    tracked = (
        await session.execute(select(TrackedObject).where(TrackedObject.slug == slug))
    ).scalar_one_or_none()
    if tracked is None:
        raise UnknownSlugError(slug)

    rows = (
        await session.execute(
            select(Ephemeris)
            .where(
                Ephemeris.spk_id == tracked.spk_id,
                Ephemeris.t_utc >= start,
                Ephemeris.t_utc <= end,
            )
            .order_by(Ephemeris.t_utc)
        )
    ).scalars().all()
    return EphemeridesResult(slug=tracked.slug, name_key=tracked.name_key, points=list(rows))


async def _existing_coverage(
    session: AsyncSession, spk_id: str, start: datetime, end: datetime
) -> set[datetime]:
    rows = (
        await session.execute(
            select(Ephemeris.t_utc).where(
                Ephemeris.spk_id == spk_id,
                Ephemeris.t_utc >= start,
                Ephemeris.t_utc <= end,
            )
        )
    ).scalars().all()
    return set(rows)


_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


def _floor_to_step(dt: datetime, step_hours: int) -> datetime:
    """Floor `dt` to the nearest step-aligned instant, anchored at the Unix
    epoch rather than at whatever wall-clock instant the caller happens to
    run at.

    Without this, `window_start = datetime.now() - 7d` would put a different
    sample grid under every run (job jitter, restarts, or simply two calls a
    few seconds apart all shift `now()`), so a previously-synced instant
    would almost never exactly equal a newly-computed expected sample —
    defeating the "never re-fetch a covered instant" invariant the courtesy
    rules depend on. Anchoring to the epoch makes the grid depend only on
    `step_hours`, so it is identical across every run.
    """
    step_seconds = step_hours * 3600
    elapsed = (dt - _EPOCH).total_seconds()
    floored_seconds = (elapsed // step_seconds) * step_seconds
    return _EPOCH + timedelta(seconds=floored_seconds)


def _missing_range(
    start: datetime, end: datetime, step_hours: int, covered: set[datetime]
) -> tuple[datetime, datetime] | None:
    """The smallest [start, end] bound spanning every uncovered expected
    sample, or None if the whole window is already covered.

    Coalescing into one bounding range (rather than one call per gap) is what
    keeps this at "one Horizons call per object per run max" (courtesy
    rules) — any already-covered samples inside the bound are skipped on
    insert rather than re-fetched individually.
    """
    step = timedelta(hours=step_hours)
    missing: list[datetime] = []
    t = start
    while t <= end:
        if t not in covered:
            missing.append(t)
        t += step
    if not missing:
        return None
    return min(missing), max(missing)


async def sync_tracked_object(
    session: AsyncSession, client: HorizonsClient, tracked: TrackedObject
) -> None:
    """Fill any missing ephemerides coverage for one tracked object."""
    now = datetime.now(timezone.utc)
    window_start = _floor_to_step(now - timedelta(days=COVERAGE_PAST_DAYS), tracked.step_hours)
    window_end = _floor_to_step(now + timedelta(days=COVERAGE_FUTURE_DAYS), tracked.step_hours)

    covered = await _existing_coverage(session, tracked.spk_id, window_start, window_end)
    missing = _missing_range(window_start, window_end, tracked.step_hours, covered)
    if missing is None:
        return

    fetch_start, fetch_end = missing
    points = await client.fetch_vectors(
        tracked.spk_id, fetch_start, fetch_end, tracked.step_hours
    )
    for t_utc, x_au, y_au, z_au in points:
        if t_utc in covered:
            continue
        session.add(
            Ephemeris(spk_id=tracked.spk_id, t_utc=t_utc, x_au=x_au, y_au=y_au, z_au=z_au)
        )
    await session.commit()


async def run_ephemeris_sync(session: AsyncSession, client: HorizonsClient) -> None:
    """`ephemeris_sync` worker job body: sync every active tracked object."""
    tracked_objects = (
        await session.execute(select(TrackedObject).where(TrackedObject.active.is_(True)))
    ).scalars().all()
    for tracked in tracked_objects:
        await sync_tracked_object(session, client, tracked)
