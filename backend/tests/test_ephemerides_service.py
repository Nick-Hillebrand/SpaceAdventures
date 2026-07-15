"""Unit tests for app/services/ephemerides_service.py
(22-ephemeris-and-mission-replay.md — Foundation).

Covers: range validation, unknown-slug handling, coverage gap-fill logic
(the "never re-fetch an already-covered instant" invariant that keeps the
worker at one Horizons call per object per run — courtesy rules), and the
`run_ephemeris_sync` job body.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.models.ephemerides import Ephemeris, TrackedObject
from app.services import ephemerides_service
from app.services.ephemerides_service import UnknownSlugError


class FakeHorizonsClient:
    """Records every fetch_vectors() call and returns canned points spanning
    exactly the requested range at the requested step, so callers can assert
    both call count (courtesy rules) and returned coverage."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, datetime, datetime, int]] = []

    async def fetch_vectors(self, spk_id, start, stop, step_hours):
        self.calls.append((spk_id, start, stop, step_hours))
        points = []
        step = timedelta(hours=step_hours)
        t = start
        while t <= stop:
            points.append((t, 1.0, 2.0, 3.0))
            t += step
        return points


async def _make_tracked(db_session, spk_id="-170", slug="jwst", step_hours=24) -> TrackedObject:
    tracked = TrackedObject(
        spk_id=spk_id,
        slug=slug,
        name_key="spacecraft.jwst",
        kind="spacecraft",
        active=True,
        step_hours=step_hours,
    )
    db_session.add(tracked)
    await db_session.commit()
    await db_session.refresh(tracked)
    return tracked


# ---------------------------------------------------------------------------
# get_ephemerides — range validation + unknown slug
# ---------------------------------------------------------------------------


async def test_get_ephemerides_unknown_slug_raises(db_session):
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    end = datetime(2024, 1, 2, tzinfo=timezone.utc)
    with pytest.raises(UnknownSlugError):
        await ephemerides_service.get_ephemerides(db_session, "no-such-slug", start, end)


async def test_get_ephemerides_end_before_start_raises_value_error(db_session):
    await _make_tracked(db_session)
    start = datetime(2024, 1, 2, tzinfo=timezone.utc)
    end = datetime(2024, 1, 1, tzinfo=timezone.utc)
    with pytest.raises(ValueError):
        await ephemerides_service.get_ephemerides(db_session, "jwst", start, end)


async def test_get_ephemerides_range_too_wide_raises_value_error(db_session):
    await _make_tracked(db_session)
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    end = start + timedelta(days=ephemerides_service.MAX_RANGE_DAYS + 1)
    with pytest.raises(ValueError):
        await ephemerides_service.get_ephemerides(db_session, "jwst", start, end)


async def test_get_ephemerides_range_at_max_days_is_allowed(db_session):
    await _make_tracked(db_session)
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    end = start + timedelta(days=ephemerides_service.MAX_RANGE_DAYS)
    result = await ephemerides_service.get_ephemerides(db_session, "jwst", start, end)
    assert result.points == []


async def test_get_ephemerides_returns_only_points_in_range(db_session):
    tracked = await _make_tracked(db_session)
    base = datetime(2024, 1, 1, tzinfo=timezone.utc)
    for i in range(5):
        db_session.add(
            Ephemeris(spk_id=tracked.spk_id, t_utc=base + timedelta(days=i), x_au=i, y_au=i, z_au=i)
        )
    await db_session.commit()

    result = await ephemerides_service.get_ephemerides(
        db_session, "jwst", base + timedelta(days=1), base + timedelta(days=3)
    )
    assert [p.x_au for p in result.points] == [1, 2, 3]
    assert result.slug == "jwst"
    assert result.name_key == "spacecraft.jwst"


# ---------------------------------------------------------------------------
# _missing_range
# ---------------------------------------------------------------------------


def test_missing_range_returns_none_when_fully_covered():
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    end = start + timedelta(hours=48)
    covered = {start, start + timedelta(hours=24), end}
    assert ephemerides_service._missing_range(start, end, 24, covered) is None


def test_missing_range_bounds_uncovered_gap():
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    end = start + timedelta(hours=72)
    # Only the first and last samples are covered — the middle two are gaps.
    covered = {start, end}
    bound = ephemerides_service._missing_range(start, end, 24, covered)
    assert bound == (start + timedelta(hours=24), start + timedelta(hours=48))


def test_missing_range_covers_whole_window_when_nothing_covered():
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    end = start + timedelta(hours=24)
    bound = ephemerides_service._missing_range(start, end, 24, set())
    assert bound == (start, end)


# ---------------------------------------------------------------------------
# sync_tracked_object — coverage gap-fill (the courtesy-rules invariant)
# ---------------------------------------------------------------------------


async def test_sync_tracked_object_fetches_full_window_when_empty(db_session):
    tracked = await _make_tracked(db_session, step_hours=24)
    fake = FakeHorizonsClient()

    await ephemerides_service.sync_tracked_object(db_session, fake, tracked)

    assert len(fake.calls) == 1
    rows = (await db_session.execute(select(Ephemeris))).scalars().all()
    assert len(rows) > 0


async def test_sync_tracked_object_skips_horizons_call_when_already_covered(db_session):
    tracked = await _make_tracked(db_session, step_hours=24)
    now = datetime.now(timezone.utc)
    window_start = ephemerides_service._floor_to_step(
        now - timedelta(days=ephemerides_service.COVERAGE_PAST_DAYS), tracked.step_hours
    )
    window_end = ephemerides_service._floor_to_step(
        now + timedelta(days=ephemerides_service.COVERAGE_FUTURE_DAYS), tracked.step_hours
    )

    # Pre-seed every expected sample in the coverage window, on the same
    # epoch-anchored grid `sync_tracked_object` itself will compute.
    t = window_start
    while t <= window_end:
        db_session.add(Ephemeris(spk_id=tracked.spk_id, t_utc=t, x_au=1.0, y_au=2.0, z_au=3.0))
        t += timedelta(hours=tracked.step_hours)
    await db_session.commit()

    fake = FakeHorizonsClient()
    await ephemerides_service.sync_tracked_object(db_session, fake, tracked)

    assert fake.calls == [], "already-covered window must not trigger a Horizons call"


async def test_sync_tracked_object_does_not_duplicate_existing_rows(db_session):
    """A partially-covered window still only issues one bounding fetch, and
    already-covered instants inside that bound are skipped on insert rather
    than duplicated (would violate the composite PK)."""
    tracked = await _make_tracked(db_session, step_hours=24)
    now = datetime.now(timezone.utc)
    window_start = ephemerides_service._floor_to_step(
        now - timedelta(days=ephemerides_service.COVERAGE_PAST_DAYS), tracked.step_hours
    )

    # Seed only the very first sample.
    db_session.add(
        Ephemeris(spk_id=tracked.spk_id, t_utc=window_start, x_au=9.0, y_au=9.0, z_au=9.0)
    )
    await db_session.commit()

    fake = FakeHorizonsClient()
    await ephemerides_service.sync_tracked_object(db_session, fake, tracked)

    assert len(fake.calls) == 1
    rows = (await db_session.execute(
        select(Ephemeris).where(Ephemeris.t_utc == window_start)
    )).scalars().all()
    assert len(rows) == 1
    # The pre-existing row's values must survive untouched (not overwritten
    # by the synced fetch's placeholder values).
    assert rows[0].x_au == 9.0


# ---------------------------------------------------------------------------
# run_ephemeris_sync — job body
# ---------------------------------------------------------------------------


async def test_run_ephemeris_sync_only_syncs_active_objects(db_session):
    active = await _make_tracked(db_session, spk_id="-170", slug="active-obj")
    inactive = TrackedObject(
        spk_id="-31",
        slug="inactive-obj",
        name_key="spacecraft.inactive",
        kind="spacecraft",
        active=False,
        step_hours=24,
    )
    db_session.add(inactive)
    await db_session.commit()

    fake = FakeHorizonsClient()
    await ephemerides_service.run_ephemeris_sync(db_session, fake)

    synced_spk_ids = {call[0] for call in fake.calls}
    assert active.spk_id in synced_spk_ids
    assert inactive.spk_id not in synced_spk_ids
