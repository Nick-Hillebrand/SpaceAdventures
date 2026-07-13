"""Tests for Postgres advisory locks (17-worker-and-scheduling.md P3.2)."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from app.services.advisory_lock import _job_key, release_job_lock, try_job_lock


def test_job_key_is_stable_across_calls():
    assert _job_key("launches_sync") == _job_key("launches_sync")


def test_job_key_differs_per_name():
    assert _job_key("launches_sync") != _job_key("notification_drain")


async def test_try_job_lock_always_true_on_sqlite(db_session):
    assert await try_job_lock(db_session, "launches_sync") is True


async def test_release_job_lock_noop_on_sqlite(db_session):
    # Must not raise even though nothing was ever locked.
    await release_job_lock(db_session, "launches_sync")


def _mock_session(dialect_name: str, scalar_result: bool | None = None):
    session = MagicMock()
    bind = MagicMock()
    bind.dialect.name = dialect_name
    session.get_bind.return_value = bind
    result = MagicMock()
    result.scalar_one.return_value = scalar_result
    session.execute = AsyncMock(return_value=result)
    return session


async def test_try_job_lock_acquires_on_postgres():
    session = _mock_session("postgresql", scalar_result=True)
    acquired = await try_job_lock(session, "launches_sync")
    assert acquired is True
    session.execute.assert_awaited_once()


async def test_try_job_lock_denied_on_postgres():
    session = _mock_session("postgresql", scalar_result=False)
    acquired = await try_job_lock(session, "launches_sync")
    assert acquired is False


async def test_release_job_lock_issues_unlock_on_postgres():
    session = _mock_session("postgresql")
    await release_job_lock(session, "launches_sync")
    session.execute.assert_awaited_once()
