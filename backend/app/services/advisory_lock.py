"""Postgres advisory locks for job-level mutual exclusion (17-worker-and-scheduling.md P3.2).

Makes an accidental double-worker deployment safe: every job body acquires
this lock before doing any work and skips silently if it can't. On SQLite
(dev, single-worker by contract) this is a no-op that always "succeeds" —
there is only ever one worker locally, so there is nothing to serialize
against.

# CONCURRENCY: requires Postgres row lock in multi-worker deployments
"""
from __future__ import annotations

import zlib

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


def _job_key(name: str) -> int:
    """Stable 64-bit-safe key derived from the job name.

    `pg_try_advisory_lock` takes a bigint; CRC32 comfortably fits and is
    stable across processes/restarts (unlike Python's salted `hash()`).
    """
    return zlib.crc32(name.encode("utf-8"))


async def try_job_lock(session: AsyncSession, name: str) -> bool:
    """Attempt to acquire the advisory lock for job `name`.

    Returns True if acquired (caller must release it), False if another
    worker already holds it (caller must skip this run). Always True on
    SQLite, where there is no cross-process lock to contend for.
    """
    bind = session.get_bind()
    if bind.dialect.name != "postgresql":
        return True
    result = await session.execute(
        text("SELECT pg_try_advisory_lock(:key)"), {"key": _job_key(name)}
    )
    return bool(result.scalar_one())


async def release_job_lock(session: AsyncSession, name: str) -> None:
    """Release the advisory lock for job `name`. No-op on SQLite."""
    bind = session.get_bind()
    if bind.dialect.name != "postgresql":
        return
    await session.execute(
        text("SELECT pg_advisory_unlock(:key)"), {"key": _job_key(name)}
    )
