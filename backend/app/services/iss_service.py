"""ISS tracking service with N2YO quota guard and TTL-based caching.

Cache TTLs:
  positions  – 300 s (5 min), shared for all users
  TLE        – 21 600 s (6 hr)
  passes     – 3 600 s (1 hr) per unique (lat, lng, alt)

Quota guard (per Architecture/05-iss-tracker.md):
  1. Acquire module-level asyncio.Lock (_QUOTA_LOCK from n2yo_client)
  2. Reset window if > 1 h has elapsed
  3. If used >= cap → return cached data with quota_exhausted=True, or raise N2YOError
  4. Call N2YO, increment used, commit, release lock in finally
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import IssPassSet, IssPositionBatch, IssTle, N2yoQuota
from app.services.n2yo_client import N2YOClient, N2YOError, _QUOTA_LOCK

POSITIONS_TTL = 300      # seconds
TLE_TTL = 21_600          # 6 hours
PASSES_TTL = 3_600        # 1 hour

PassType = Literal["visual", "radio"]


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _age_seconds(fetched_at: datetime) -> float:
    return (_utcnow() - fetched_at).total_seconds()


# ── quota helpers ─────────────────────────────────────────────────────────────


async def _get_or_create_quota(session: AsyncSession, cap: int) -> N2yoQuota:
    row = await session.get(N2yoQuota, 1)
    if row is None:
        row = N2yoQuota(id=1, window_start=_utcnow(), used=0)
        session.add(row)
        await session.commit()
        await session.refresh(row)
    return row


async def _check_and_increment_quota(
    session: AsyncSession, cap: int
) -> tuple[N2yoQuota, bool]:
    """Check quota and pre-increment.

    Returns (quota_row, quota_exceeded).
    Must be called while holding _QUOTA_LOCK.
    """
    row = await _get_or_create_quota(session, cap)

    # Reset window if >= 1 hour has elapsed
    if _age_seconds(row.window_start) >= 3600:
        row.window_start = _utcnow()
        row.used = 0

    if row.used >= cap:
        return row, True

    row.used += 1
    await session.commit()
    await session.refresh(row)
    return row, False


async def get_quota(session: AsyncSession, cap: int) -> N2yoQuota:
    return await _get_or_create_quota(session, cap)


# ── positions ─────────────────────────────────────────────────────────────────


def _enrich_positions(raw: list[dict]) -> list[dict]:
    """Add timestamp_ms = timestamp * 1000 to each position entry (P11)."""
    result = []
    for p in raw:
        entry = dict(p)
        if "timestamp" in entry:
            entry["timestamp_ms"] = int(entry["timestamp"]) * 1000
        result.append(entry)
    return result


async def get_positions(
    session: AsyncSession, client: N2YOClient, cap: int
) -> tuple[list[dict], datetime, bool, bool]:
    """Returns (positions, fetched_at, cached, quota_exhausted)."""
    batch = await session.get(IssPositionBatch, 1)
    if batch is not None and _age_seconds(batch.fetched_at) < POSITIONS_TTL:
        return json.loads(batch.positions), batch.fetched_at, True, False

    async with _QUOTA_LOCK:
        # Re-check cache inside lock to avoid double-fetch
        batch = await session.get(IssPositionBatch, 1)
        if batch is not None and _age_seconds(batch.fetched_at) < POSITIONS_TTL:
            return json.loads(batch.positions), batch.fetched_at, True, False

        quota, exceeded = await _check_and_increment_quota(session, cap)
        if exceeded:
            if batch is not None:
                return json.loads(batch.positions), batch.fetched_at, True, True
            raise N2YOError("N2YO_QUOTA_EXHAUSTED", "N2YO quota exhausted", 429)

        try:
            data = await client.get_positions()
        except N2YOError:
            if batch is not None:
                return json.loads(batch.positions), batch.fetched_at, True, False
            raise

    raw_positions = data.get("positions") or []
    positions = _enrich_positions(raw_positions)
    now = _utcnow()

    if batch is None:
        batch = IssPositionBatch(id=1, positions=json.dumps(positions), fetched_at=now)
        session.add(batch)
    else:
        batch.positions = json.dumps(positions)
        batch.fetched_at = now
    await session.commit()
    return positions, now, False, False


# ── TLE ───────────────────────────────────────────────────────────────────────


async def get_tle(
    session: AsyncSession, client: N2YOClient, cap: int
) -> tuple[IssTle, bool, bool]:
    """Returns (tle_row, cached, quota_exhausted)."""
    tle = await session.get(IssTle, 1)
    if tle is not None and _age_seconds(tle.fetched_at) < TLE_TTL:
        return tle, True, False

    async with _QUOTA_LOCK:
        tle = await session.get(IssTle, 1)
        if tle is not None and _age_seconds(tle.fetched_at) < TLE_TTL:
            return tle, True, False

        quota, exceeded = await _check_and_increment_quota(session, cap)
        if exceeded:
            if tle is not None:
                return tle, True, True
            raise N2YOError("N2YO_QUOTA_EXHAUSTED", "N2YO quota exhausted", 429)

        try:
            data = await client.get_tle()
        except N2YOError:
            if tle is not None:
                return tle, True, False
            raise

    raw_tle = data.get("tle", "")
    lines = [line.strip() for line in raw_tle.replace("\\n", "\n").split("\n") if line.strip()]
    line0 = lines[0] if len(lines) > 0 else ""
    line1 = lines[1] if len(lines) > 1 else ""
    line2 = lines[2] if len(lines) > 2 else ""
    now = _utcnow()

    if tle is None:
        tle = IssTle(id=1, tle_line0=line0, tle_line1=line1, tle_line2=line2, fetched_at=now)
        session.add(tle)
    else:
        tle.tle_line0 = line0
        tle.tle_line1 = line1
        tle.tle_line2 = line2
        tle.fetched_at = now
    await session.commit()
    await session.refresh(tle)
    return tle, False, False


# ── passes ────────────────────────────────────────────────────────────────────


async def _get_pass_set(
    session: AsyncSession, pass_type: PassType, lat: float, lng: float, alt: float
) -> IssPassSet | None:
    result = await session.execute(
        select(IssPassSet).where(
            IssPassSet.pass_type == pass_type,
            IssPassSet.observer_lat == lat,
            IssPassSet.observer_lng == lng,
            IssPassSet.observer_alt == alt,
        )
    )
    return result.scalar_one_or_none()


async def get_passes(
    session: AsyncSession,
    client: N2YOClient,
    cap: int,
    pass_type: PassType,
    lat: float,
    lng: float,
    alt: float,
) -> tuple[list[dict], datetime, bool, bool]:
    """Returns (passes, fetched_at, cached, quota_exhausted)."""
    existing = await _get_pass_set(session, pass_type, lat, lng, alt)
    if existing is not None and _age_seconds(existing.fetched_at) < PASSES_TTL:
        return json.loads(existing.passes_json), existing.fetched_at, True, False

    async with _QUOTA_LOCK:
        existing = await _get_pass_set(session, pass_type, lat, lng, alt)
        if existing is not None and _age_seconds(existing.fetched_at) < PASSES_TTL:
            return json.loads(existing.passes_json), existing.fetched_at, True, False

        quota, exceeded = await _check_and_increment_quota(session, cap)
        if exceeded:
            if existing is not None:
                return json.loads(existing.passes_json), existing.fetched_at, True, True
            raise N2YOError("N2YO_QUOTA_EXHAUSTED", "N2YO quota exhausted", 429)

        try:
            if pass_type == "visual":
                data = await client.get_visual_passes(lat, lng, alt)
            else:
                data = await client.get_radio_passes(lat, lng, alt)
        except N2YOError:
            if existing is not None:
                return json.loads(existing.passes_json), existing.fetched_at, True, False
            raise

    passes = data.get("passes") or []
    now = _utcnow()

    if existing is None:
        ps = IssPassSet(
            pass_type=pass_type,
            observer_lat=lat,
            observer_lng=lng,
            observer_alt=alt,
            passes_json=json.dumps(passes),
            fetched_at=now,
        )
        session.add(ps)
    else:
        existing.passes_json = json.dumps(passes)
        existing.fetched_at = now
    await session.commit()
    return passes, now, False, False
