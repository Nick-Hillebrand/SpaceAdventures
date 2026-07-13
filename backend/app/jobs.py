"""Job registry — single source of truth for every recurring background job
(17-worker-and-scheduling.md P3.2). Registered by both the dedicated worker
process (`worker.py`) and, in dev only, the web process when
`SCHEDULER_IN_APP=1` (`main.py`) — so there is exactly one place that defines
what jobs exist and how often they run.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Awaitable, Callable

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import delete

from app import observability
from app.config import Settings
from app.database import get_sessionmaker
from app.models.job_status import JobStatus
from app.models.rate_limit import RateLimitEvent
from app.services import launches_service, notification_service
from app.services.advisory_lock import release_job_lock, try_job_lock

logger = logging.getLogger(__name__)

_RATE_LIMIT_EVENT_RETENTION_HOURS = 24

# 26-performance.md §1.5 — logged and Sentry-warned on breach, not enforced.
JOB_DURATION_BUDGET_SECONDS: dict[str, float] = {
    "notification_drain": 60,
    "worker_heartbeat": 10,
}
_DEFAULT_JOB_DURATION_BUDGET_SECONDS = 120

# 17-…md P3.5 — admin health reports a job "stale" once it hasn't succeeded
# within roughly 4x its own interval.
JOB_STALENESS_SECONDS: dict[str, int] = {
    "launches_sync": 4 * 30 * 60,
    "notification_drain": 4 * 60,
    "rate_limit_purge": 4 * 24 * 60 * 60,
    "worker_heartbeat": 5 * 60,
}


async def _record_success(job_name: str) -> None:
    async with get_sessionmaker()() as session:
        row = await session.get(JobStatus, job_name)
        if row is None:
            row = JobStatus(job_name=job_name)
            session.add(row)
        row.last_success_at = datetime.now(timezone.utc)
        row.last_error = None
        await session.commit()


async def _record_error(job_name: str, exc: Exception) -> None:
    scrubbed = notification_service.scrub_error(exc)
    async with get_sessionmaker()() as session:
        row = await session.get(JobStatus, job_name)
        if row is None:
            row = JobStatus(job_name=job_name)
            session.add(row)
        row.last_error = scrubbed
        await session.commit()


def _make_runner(name: str, body: Callable[[], Awaitable[None]]) -> Callable[[], Awaitable[None]]:
    """Wrap a job body with the advisory lock / timing / error-containment
    rules every job must follow (17-…md P3.2)."""

    async def _run() -> None:
        async with get_sessionmaker()() as lock_session:
            if not await try_job_lock(lock_session, name):
                logger.info("job %s: skipped, lock held by another worker", name)
                return
            try:
                start = time.monotonic()
                try:
                    await body()
                except Exception as exc:  # noqa: BLE001 — one bad job must not kill the scheduler
                    duration_ms = (time.monotonic() - start) * 1000
                    logger.error(
                        "job %s failed after %.0fms: %s", name, duration_ms, exc
                    )
                    observability.capture_exception(exc)
                    await _record_error(name, exc)
                else:
                    duration_ms = (time.monotonic() - start) * 1000
                    budget = JOB_DURATION_BUDGET_SECONDS.get(
                        name, _DEFAULT_JOB_DURATION_BUDGET_SECONDS
                    )
                    if duration_ms / 1000 > budget:
                        logger.warning(
                            "job %s exceeded its %ss budget: %.0fms",
                            name, budget, duration_ms,
                        )
                    logger.info("job %s succeeded in %.0fms", name, duration_ms)
                    await _record_success(name)
            finally:
                await release_job_lock(lock_session, name)

    return _run


async def _launches_sync_body(clients: Any, settings: Settings) -> None:
    async with get_sessionmaker()() as session:
        await launches_service.sync_launches(
            session, clients.ll2_client, translator=clients.translator
        )


async def _notification_drain_body(clients: Any, settings: Settings) -> None:
    async with get_sessionmaker()() as session:
        await notification_service.drain_queue(session, settings)


async def _rate_limit_purge_body(clients: Any, settings: Settings) -> None:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=_RATE_LIMIT_EVENT_RETENTION_HOURS)
    async with get_sessionmaker()() as session:
        await session.execute(delete(RateLimitEvent).where(RateLimitEvent.created_at < cutoff))
        await session.commit()


async def _worker_heartbeat_body(clients: Any, settings: Settings) -> None:
    await _record_success("worker_heartbeat")


@dataclass
class JobSpec:
    name: str
    trigger: str
    kwargs: dict[str, Any]


def register_jobs(scheduler: AsyncIOScheduler, settings: Settings, clients: Any) -> None:
    """Register every recurring job on `scheduler`. Called once by the worker
    entrypoint (and, in dev, by the web process under `SCHEDULER_IN_APP=1`)."""

    jobs = [
        JobSpec("launches_sync", "interval", {"minutes": settings.ll2_sync_interval_minutes}),
        JobSpec("notification_drain", "interval", {"minutes": 1}),
        JobSpec("rate_limit_purge", "interval", {"hours": _RATE_LIMIT_EVENT_RETENTION_HOURS}),
        JobSpec("worker_heartbeat", "interval", {"seconds": 30}),
    ]
    bodies: dict[str, Callable[[Any, Settings], Awaitable[None]]] = {
        "launches_sync": _launches_sync_body,
        "notification_drain": _notification_drain_body,
        "rate_limit_purge": _rate_limit_purge_body,
        "worker_heartbeat": _worker_heartbeat_body,
    }

    for job in jobs:
        body = bodies[job.name]

        async def _bound_body(body=body) -> None:
            await body(clients, settings)

        scheduler.add_job(
            _make_runner(job.name, _bound_body),
            trigger=job.trigger,
            # APScheduler's IntervalTrigger otherwise waits a full interval
            # before its first run — on a fresh deploy/dev boot that leaves
            # launches_sync (interval: 30min) with an empty launches table
            # for half an hour before anyone sees a rocket launch. Fire once
            # immediately, then follow the configured interval as usual.
            next_run_time=datetime.now(timezone.utc),
            **job.kwargs,
        )
