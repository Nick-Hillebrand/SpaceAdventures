"""Tests for the job registry (17-worker-and-scheduling.md P3.2)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app import jobs
from app.models.job_status import JobStatus
from app.models.rate_limit import RateLimitEvent


@pytest.fixture(autouse=True)
def _patch_sessionmaker(db_engine):
    """Every job function grabs its own session via `get_sessionmaker()` — bind
    that to the test's in-memory engine instead of the (uninitialized) global
    engine."""
    factory = async_sessionmaker(db_engine, expire_on_commit=False, class_=AsyncSession)
    with patch("app.jobs.get_sessionmaker", return_value=factory):
        yield factory


# ---------------------------------------------------------------------------
# _record_success / _record_error
# ---------------------------------------------------------------------------


async def test_record_success_creates_row(db_session):
    await jobs._record_success("launches_sync")
    row = await db_session.get(JobStatus, "launches_sync")
    assert row is not None
    assert row.last_success_at is not None
    assert row.last_error is None


async def test_record_success_updates_existing_and_clears_error(db_session):
    db_session.add(JobStatus(job_name="launches_sync", last_error="boom"))
    await db_session.commit()

    await jobs._record_success("launches_sync")

    db_session.expire_all()
    row = await db_session.get(JobStatus, "launches_sync")
    assert row.last_error is None
    assert row.last_success_at is not None


async def test_record_error_creates_row_with_scrubbed_message(db_session):
    await jobs._record_error("launches_sync", ValueError("raw secret leak"))
    row = await db_session.get(JobStatus, "launches_sync")
    assert row is not None
    assert row.last_error is not None


async def test_record_error_updates_existing_row(db_session):
    db_session.add(JobStatus(job_name="launches_sync"))
    await db_session.commit()

    await jobs._record_error("launches_sync", RuntimeError("boom"))

    db_session.expire_all()
    row = await db_session.get(JobStatus, "launches_sync")
    assert row.last_error is not None


# ---------------------------------------------------------------------------
# _make_runner
# ---------------------------------------------------------------------------


async def test_make_runner_skips_when_lock_not_acquired(db_session):
    body = AsyncMock()
    runner = jobs._make_runner("launches_sync", body)

    with patch("app.jobs.try_job_lock", new=AsyncMock(return_value=False)), \
         patch("app.jobs.release_job_lock", new=AsyncMock()) as mock_release:
        await runner()

    body.assert_not_called()
    mock_release.assert_not_called()


async def test_make_runner_success_records_success(db_session):
    body = AsyncMock()
    runner = jobs._make_runner("launches_sync", body)

    await runner()

    body.assert_awaited_once()
    row = await db_session.get(JobStatus, "launches_sync")
    assert row.last_success_at is not None
    assert row.last_error is None


async def test_make_runner_exception_records_error_and_reports_sentry(db_session):
    body = AsyncMock(side_effect=ValueError("job blew up"))
    runner = jobs._make_runner("launches_sync", body)

    with patch("app.jobs.observability.capture_exception") as mock_capture:
        await runner()

    mock_capture.assert_called_once()
    row = await db_session.get(JobStatus, "launches_sync")
    assert row.last_error is not None


async def test_make_runner_releases_lock_even_on_exception(db_session):
    body = AsyncMock(side_effect=ValueError("boom"))
    runner = jobs._make_runner("launches_sync", body)

    with patch("app.jobs.release_job_lock", new=AsyncMock()) as mock_release:
        await runner()

    mock_release.assert_awaited_once()


async def test_make_runner_warns_on_budget_breach(db_session):
    body = AsyncMock()
    runner = jobs._make_runner("notification_drain", body)  # 60s budget

    # time.monotonic() is called twice per run (start, then elapsed check);
    # patch only `app.jobs.time` (not the global time module) so asyncio's own
    # internals — which also use time.monotonic — keep working normally.
    fake_time = MagicMock()
    fake_time.monotonic.side_effect = [0.0, 61.0]
    with patch("app.jobs.time", fake_time), \
         patch("app.jobs.logger.warning") as mock_warning:
        await runner()

    mock_warning.assert_called_once()


async def test_make_runner_no_warning_within_budget(db_session):
    body = AsyncMock()
    runner = jobs._make_runner("notification_drain", body)

    with patch("app.jobs.logger.warning") as mock_warning:
        await runner()

    mock_warning.assert_not_called()


async def test_make_runner_uses_default_budget_for_unknown_job(db_session):
    body = AsyncMock()
    runner = jobs._make_runner("some_other_job", body)

    with patch("app.jobs.logger.warning") as mock_warning:
        await runner()

    mock_warning.assert_not_called()


# ---------------------------------------------------------------------------
# Job bodies
# ---------------------------------------------------------------------------


async def test_launches_sync_body_delegates_to_service():
    clients = SimpleNamespace(ll2_client=MagicMock(), translator=MagicMock())
    settings = MagicMock()

    with patch("app.jobs.launches_service.sync_launches", new=AsyncMock()) as mock_sync:
        await jobs._launches_sync_body(clients, settings)

    mock_sync.assert_awaited_once()
    _, kwargs = mock_sync.call_args
    assert kwargs["translator"] is clients.translator


async def test_notification_drain_body_delegates_to_service():
    clients = SimpleNamespace()
    settings = MagicMock()

    with patch("app.jobs.notification_service.drain_queue", new=AsyncMock()) as mock_drain:
        await jobs._notification_drain_body(clients, settings)

    mock_drain.assert_awaited_once()


async def test_rate_limit_purge_body_deletes_old_rows(db_session):
    old = datetime.now(timezone.utc) - timedelta(hours=48)
    recent = datetime.now(timezone.utc) - timedelta(hours=1)
    db_session.add_all([
        RateLimitEvent(bucket="login", ip_hash="old", created_at=old),
        RateLimitEvent(bucket="login", ip_hash="recent", created_at=recent),
    ])
    await db_session.commit()

    await jobs._rate_limit_purge_body(SimpleNamespace(), MagicMock())

    db_session.expire_all()
    from sqlalchemy import select
    result = await db_session.execute(select(RateLimitEvent))
    remaining = result.scalars().all()
    assert len(remaining) == 1
    assert remaining[0].ip_hash == "recent"


async def test_worker_heartbeat_body_records_success(db_session):
    await jobs._worker_heartbeat_body(SimpleNamespace(), MagicMock())
    row = await db_session.get(JobStatus, "worker_heartbeat")
    assert row is not None
    assert row.last_success_at is not None


# ---------------------------------------------------------------------------
# register_jobs
# ---------------------------------------------------------------------------


def test_register_jobs_registers_all_five_jobs():
    scheduler = MagicMock()
    settings = MagicMock(ll2_sync_interval_minutes=30)
    clients = SimpleNamespace(
        ll2_client=MagicMock(), translator=MagicMock(), horizons_client=MagicMock()
    )

    jobs.register_jobs(scheduler, settings, clients)

    assert scheduler.add_job.call_count == 5
    kwargs_list = [call.kwargs for call in scheduler.add_job.call_args_list]
    triggers = {kw["trigger"] for kw in kwargs_list}
    assert triggers == {"interval"}


def test_register_jobs_fires_immediately_on_registration():
    """Regression test: without an explicit `next_run_time`, APScheduler's
    IntervalTrigger waits a full interval before its first run, leaving
    launches_sync (interval: 30min) with an empty launches table for half an
    hour after every fresh deploy/dev boot."""
    scheduler = MagicMock()
    settings = MagicMock(ll2_sync_interval_minutes=30)
    clients = SimpleNamespace(ll2_client=MagicMock(), translator=MagicMock())

    before = datetime.now(timezone.utc)
    jobs.register_jobs(scheduler, settings, clients)
    after = datetime.now(timezone.utc)

    for call in scheduler.add_job.call_args_list:
        next_run_time = call.kwargs["next_run_time"]
        assert before <= next_run_time <= after


def test_register_jobs_uses_configured_sync_interval():
    scheduler = MagicMock()
    settings = MagicMock(ll2_sync_interval_minutes=45)
    clients = SimpleNamespace(ll2_client=MagicMock(), translator=MagicMock())

    jobs.register_jobs(scheduler, settings, clients)

    launches_call = scheduler.add_job.call_args_list[0]
    assert launches_call.kwargs["minutes"] == 45
