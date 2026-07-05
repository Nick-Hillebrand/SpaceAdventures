"""Tests for the N2YO quota guard (concurrent boundary, window reset)."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest

from app.models import N2yoQuota
from app.services import iss_service
from app.services.n2yo_client import N2YOError


def _make_quota(used: int, window_offset_seconds: int = 0) -> N2yoQuota:
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    return N2yoQuota(
        id=1,
        window_start=now - timedelta(seconds=window_offset_seconds),
        used=used,
    )


# ── get_or_create_quota ───────────────────────────────────────────────────────


async def test_get_or_create_quota_creates_row(db_session):
    quota = await iss_service._get_or_create_quota(db_session, cap=900)
    assert quota.id == 1
    assert quota.used == 0


async def test_get_or_create_quota_returns_existing(db_session):
    row = N2yoQuota(id=1, window_start=datetime(2024, 1, 1), used=50)
    db_session.add(row)
    await db_session.commit()

    quota = await iss_service._get_or_create_quota(db_session, cap=900)
    assert quota.used == 50


# ── window reset ──────────────────────────────────────────────────────────────


async def test_window_resets_after_one_hour(db_session):
    row = N2yoQuota(
        id=1,
        window_start=datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=2),
        used=800,
    )
    db_session.add(row)
    await db_session.commit()

    quota, exceeded = await iss_service._check_and_increment_quota(db_session, cap=900)
    assert quota.used == 1
    assert exceeded is False


async def test_window_does_not_reset_within_hour(db_session):
    row = N2yoQuota(
        id=1,
        window_start=datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(minutes=30),
        used=100,
    )
    db_session.add(row)
    await db_session.commit()

    quota, exceeded = await iss_service._check_and_increment_quota(db_session, cap=900)
    assert quota.used == 101
    assert exceeded is False


# ── quota cap enforcement ─────────────────────────────────────────────────────


async def test_quota_exceeded_when_at_cap(db_session):
    row = N2yoQuota(
        id=1,
        window_start=datetime.now(timezone.utc).replace(tzinfo=None),
        used=900,
    )
    db_session.add(row)
    await db_session.commit()

    quota, exceeded = await iss_service._check_and_increment_quota(db_session, cap=900)
    assert exceeded is True
    # used should NOT be incremented when exceeded
    assert quota.used == 900


async def test_quota_not_exceeded_at_cap_minus_one(db_session):
    row = N2yoQuota(
        id=1,
        window_start=datetime.now(timezone.utc).replace(tzinfo=None),
        used=899,
    )
    db_session.add(row)
    await db_session.commit()

    quota, exceeded = await iss_service._check_and_increment_quota(db_session, cap=900)
    assert exceeded is False
    assert quota.used == 900


# ── concurrent boundary: two simultaneous calls at used=899 ──────────────────


async def test_concurrent_calls_at_boundary(db_session):
    """Only one of two concurrent calls at used=899 should succeed; the other
    should see quota exhausted."""
    row = N2yoQuota(
        id=1,
        window_start=datetime.now(timezone.utc).replace(tzinfo=None),
        used=899,
    )
    db_session.add(row)
    await db_session.commit()

    results = []

    async def attempt():
        quota, exceeded = await iss_service._check_and_increment_quota(db_session, cap=900)
        results.append(exceeded)

    await asyncio.gather(attempt(), attempt())

    # Exactly one should exceed
    assert results.count(False) == 1
    assert results.count(True) == 1

    # Final used should be exactly 900
    quota = await db_session.get(N2yoQuota, 1)
    assert quota.used == 900


# ── get_quota ─────────────────────────────────────────────────────────────────


async def test_get_quota_creates_if_missing(db_session):
    quota = await iss_service.get_quota(db_session, cap=900)
    assert quota.id == 1
    assert quota.used == 0
