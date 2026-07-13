"""Direct unit tests of iss_service for async coverage instrumentation."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import httpx
import pytest
import respx

from app.config import Settings
from app.models import IssPassSet, IssPositionBatch, IssTle, N2yoQuota
from app.services import iss_service
from app.services.n2yo_client import N2YOClient, N2YOError

_N2YO_BASE = "https://api.n2yo.example/rest/v1/satellite"


def _make_settings() -> Settings:
    return Settings(  # type: ignore[call-arg]
        require_secrets=False,
        n2yo_api_key="TEST",
        n2yo_base_url=_N2YO_BASE,
    )


@pytest.fixture
async def n2yo():
    c = N2YOClient(_make_settings())
    try:
        yield c
    finally:
        await c.close()


def _pos_payload(count: int = 300) -> dict:
    return {
        "info": {"satid": 25544},
        "positions": [{"satlatitude": 10.0, "satlongitude": 20.0, "timestamp": 1_700_000_000}] * count,
    }


# ── positions ─────────────────────────────────────────────────────────────────


@respx.mock
async def test_get_positions_cache_miss(db_session, n2yo):
    respx.get(f"{_N2YO_BASE}/positions/25544/0.0/0.0/0.0/300").mock(
        return_value=httpx.Response(200, json=_pos_payload())
    )
    positions, fetched_at, cached, quota_exhausted = await iss_service.get_positions(
        db_session, n2yo, cap=900
    )
    assert cached is False
    assert quota_exhausted is False
    assert len(positions) == 300
    assert positions[0]["timestamp_ms"] == 1_700_000_000 * 1000


async def test_get_positions_cache_hit(db_session, n2yo):
    db_session.add(
        IssPositionBatch(
            id=1,
            positions=[{"timestamp_ms": 1}],
            fetched_at=datetime.utcnow(),
        )
    )
    await db_session.commit()

    with respx.mock:
        route = respx.get(f"{_N2YO_BASE}/positions/25544/0.0/0.0/0.0/300")
        _, _, cached, _ = await iss_service.get_positions(db_session, n2yo, cap=900)

    assert cached is True
    assert route.called is False


@respx.mock
async def test_get_positions_stale_cache_served_on_error(db_session, n2yo):
    db_session.add(
        IssPositionBatch(
            id=1,
            positions=[{"timestamp_ms": 1}],
            fetched_at=datetime.utcnow() - timedelta(minutes=10),
        )
    )
    await db_session.commit()

    respx.get(f"{_N2YO_BASE}/positions/25544/0.0/0.0/0.0/300").mock(
        return_value=httpx.Response(200, json={"error": "bad key"})
    )
    _, _, cached, _ = await iss_service.get_positions(db_session, n2yo, cap=900)
    assert cached is True


@respx.mock
async def test_get_positions_no_cache_n2yo_error_raises(db_session, n2yo):
    respx.get(f"{_N2YO_BASE}/positions/25544/0.0/0.0/0.0/300").mock(
        return_value=httpx.Response(200, json={"error": "bad key"})
    )
    with pytest.raises(N2YOError):
        await iss_service.get_positions(db_session, n2yo, cap=900)


@respx.mock
async def test_get_positions_updates_existing_batch(db_session, n2yo):
    db_session.add(
        IssPositionBatch(
            id=1,
            positions=[{"old": True}],
            fetched_at=datetime.utcnow() - timedelta(minutes=10),
        )
    )
    await db_session.commit()

    respx.get(f"{_N2YO_BASE}/positions/25544/0.0/0.0/0.0/300").mock(
        return_value=httpx.Response(200, json=_pos_payload(5))
    )
    positions, _, cached, _ = await iss_service.get_positions(db_session, n2yo, cap=900)
    assert cached is False
    assert len(positions) == 5


# ── TLE ───────────────────────────────────────────────────────────────────────


@respx.mock
async def test_get_tle_cache_miss(db_session, n2yo):
    respx.get(f"{_N2YO_BASE}/tle/25544").mock(
        return_value=httpx.Response(
            200,
            json={"tle": "ISS\\n1 25544U 98067A\\n2 25544  51.6435"},
        )
    )
    tle, cached, quota_exhausted = await iss_service.get_tle(db_session, n2yo, cap=900)
    assert cached is False
    assert quota_exhausted is False
    assert tle.tle_line0 == "ISS"


async def test_get_tle_cache_hit(db_session, n2yo):
    db_session.add(
        IssTle(id=1, tle_line0="ISS", tle_line1="L1", tle_line2="L2", fetched_at=datetime.utcnow())
    )
    await db_session.commit()

    with respx.mock:
        route = respx.get(f"{_N2YO_BASE}/tle/25544")
        tle, cached, _ = await iss_service.get_tle(db_session, n2yo, cap=900)

    assert cached is True
    assert route.called is False


@respx.mock
async def test_get_tle_updates_existing(db_session, n2yo):
    db_session.add(
        IssTle(id=1, tle_line0="OLD", tle_line1="L1", tle_line2="L2",
               fetched_at=datetime.utcnow() - timedelta(hours=10))
    )
    await db_session.commit()

    respx.get(f"{_N2YO_BASE}/tle/25544").mock(
        return_value=httpx.Response(
            200,
            json={"tle": "NEW\\nL1_NEW\\nL2_NEW"},
        )
    )
    tle, cached, _ = await iss_service.get_tle(db_session, n2yo, cap=900)
    assert cached is False
    assert tle.tle_line0 == "NEW"


@respx.mock
async def test_get_tle_stale_served_on_error(db_session, n2yo):
    db_session.add(
        IssTle(id=1, tle_line0="ISS", tle_line1="L1", tle_line2="L2",
               fetched_at=datetime.utcnow() - timedelta(hours=10))
    )
    await db_session.commit()

    respx.get(f"{_N2YO_BASE}/tle/25544").mock(
        return_value=httpx.Response(200, json={"error": "bad key"})
    )
    tle, cached, _ = await iss_service.get_tle(db_session, n2yo, cap=900)
    assert cached is True
    assert tle.tle_line0 == "ISS"


@respx.mock
async def test_get_tle_no_cache_error_raises(db_session, n2yo):
    respx.get(f"{_N2YO_BASE}/tle/25544").mock(
        return_value=httpx.Response(200, json={"error": "bad key"})
    )
    with pytest.raises(N2YOError):
        await iss_service.get_tle(db_session, n2yo, cap=900)


# ── passes ────────────────────────────────────────────────────────────────────


def _pass_payload() -> dict:
    return {
        "info": {},
        "passes": [{"startUTC": 1_700_001_000, "duration": 120, "maxEl": 45.0}],
    }


@respx.mock
async def test_get_visual_passes_cache_miss(db_session, n2yo):
    respx.get(f"{_N2YO_BASE}/visualpasses/25544/51.5/-0.1/30.0/7/10").mock(
        return_value=httpx.Response(200, json=_pass_payload())
    )
    passes, _, cached, _ = await iss_service.get_passes(
        db_session, n2yo, cap=900, pass_type="visual", lat=51.5, lng=-0.1, alt=30.0
    )
    assert cached is False
    assert len(passes) == 1


@respx.mock
async def test_get_radio_passes_cache_miss(db_session, n2yo):
    respx.get(f"{_N2YO_BASE}/radiopasses/25544/51.5/-0.1/30.0/7/10").mock(
        return_value=httpx.Response(200, json=_pass_payload())
    )
    passes, _, cached, _ = await iss_service.get_passes(
        db_session, n2yo, cap=900, pass_type="radio", lat=51.5, lng=-0.1, alt=30.0
    )
    assert cached is False


async def test_get_passes_cache_hit(db_session, n2yo):
    db_session.add(
        IssPassSet(
            pass_type="visual",
            observer_lat=10.0, observer_lng=20.0, observer_alt=0.0,
            passes_json=[{"startUTC": 1}],
            fetched_at=datetime.utcnow(),
        )
    )
    await db_session.commit()

    with respx.mock:
        route = respx.get(f"{_N2YO_BASE}/visualpasses/25544/10.0/20.0/0.0/7/10")
        _, _, cached, _ = await iss_service.get_passes(
            db_session, n2yo, cap=900, pass_type="visual", lat=10.0, lng=20.0, alt=0.0
        )

    assert cached is True
    assert route.called is False


@respx.mock
async def test_get_passes_stale_served_on_error(db_session, n2yo):
    db_session.add(
        IssPassSet(
            pass_type="visual",
            observer_lat=10.0, observer_lng=20.0, observer_alt=0.0,
            passes_json=[{"startUTC": 1}],
            fetched_at=datetime.utcnow() - timedelta(hours=2),
        )
    )
    await db_session.commit()

    respx.get(f"{_N2YO_BASE}/visualpasses/25544/10.0/20.0/0.0/7/10").mock(
        return_value=httpx.Response(200, json={"error": "bad key"})
    )
    _, _, cached, _ = await iss_service.get_passes(
        db_session, n2yo, cap=900, pass_type="visual", lat=10.0, lng=20.0, alt=0.0
    )
    assert cached is True


@respx.mock
async def test_get_passes_no_cache_error_raises(db_session, n2yo):
    respx.get(f"{_N2YO_BASE}/visualpasses/25544/0.0/0.0/0.0/7/10").mock(
        return_value=httpx.Response(200, json={"error": "bad key"})
    )
    with pytest.raises(N2YOError):
        await iss_service.get_passes(
            db_session, n2yo, cap=900, pass_type="visual", lat=0.0, lng=0.0, alt=0.0
        )


@respx.mock
async def test_get_passes_updates_existing(db_session, n2yo):
    db_session.add(
        IssPassSet(
            pass_type="visual",
            observer_lat=0.0, observer_lng=0.0, observer_alt=0.0,
            passes_json=[{"old": True}],
            fetched_at=datetime.utcnow() - timedelta(hours=2),
        )
    )
    await db_session.commit()

    respx.get(f"{_N2YO_BASE}/visualpasses/25544/0.0/0.0/0.0/7/10").mock(
        return_value=httpx.Response(200, json=_pass_payload())
    )
    passes, _, cached, _ = await iss_service.get_passes(
        db_session, n2yo, cap=900, pass_type="visual", lat=0.0, lng=0.0, alt=0.0
    )
    assert cached is False
    assert "startUTC" in passes[0]


# ── quota exhausted paths ─────────────────────────────────────────────────────


async def test_positions_quota_exhausted_no_cache_raises(db_session, n2yo):
    db_session.add(N2yoQuota(id=1, window_start=datetime.utcnow(), used=900))
    await db_session.commit()

    with pytest.raises(N2YOError) as exc_info:
        await iss_service.get_positions(db_session, n2yo, cap=900)
    assert exc_info.value.code == "N2YO_QUOTA_EXHAUSTED"


async def test_positions_quota_exhausted_with_cache(db_session, n2yo):
    db_session.add(
        IssPositionBatch(
            id=1,
            positions=[{"quota": True}],
            fetched_at=datetime.utcnow() - timedelta(minutes=10),
        )
    )
    db_session.add(N2yoQuota(id=1, window_start=datetime.utcnow(), used=900))
    await db_session.commit()

    _, _, cached, quota_exhausted = await iss_service.get_positions(db_session, n2yo, cap=900)
    assert cached is True
    assert quota_exhausted is True


async def test_tle_quota_exhausted_no_cache_raises(db_session, n2yo):
    db_session.add(N2yoQuota(id=1, window_start=datetime.utcnow(), used=900))
    await db_session.commit()

    with pytest.raises(N2YOError):
        await iss_service.get_tle(db_session, n2yo, cap=900)


async def test_tle_quota_exhausted_with_stale_cache(db_session, n2yo):
    db_session.add(
        IssTle(id=1, tle_line0="ISS", tle_line1="L1", tle_line2="L2",
               fetched_at=datetime.utcnow() - timedelta(hours=12))
    )
    db_session.add(N2yoQuota(id=1, window_start=datetime.utcnow(), used=900))
    await db_session.commit()

    tle, cached, quota_exhausted = await iss_service.get_tle(db_session, n2yo, cap=900)
    assert cached is True
    assert quota_exhausted is True


async def test_passes_quota_exhausted_with_cache(db_session, n2yo):
    db_session.add(
        IssPassSet(
            pass_type="visual",
            observer_lat=1.0, observer_lng=1.0, observer_alt=0.0,
            passes_json=[{"old": True}],
            fetched_at=datetime.utcnow() - timedelta(hours=2),
        )
    )
    db_session.add(N2yoQuota(id=1, window_start=datetime.utcnow(), used=900))
    await db_session.commit()

    _, _, cached, quota_exhausted = await iss_service.get_passes(
        db_session, n2yo, cap=900, pass_type="visual", lat=1.0, lng=1.0, alt=0.0
    )
    assert cached is True
    assert quota_exhausted is True


# ── _enrich_positions ─────────────────────────────────────────────────────────


def test_enrich_positions_adds_timestamp_ms():
    raw = [{"timestamp": 1_700_000_000, "satlatitude": 10.0}]
    enriched = iss_service._enrich_positions(raw)
    assert enriched[0]["timestamp_ms"] == 1_700_000_000_000


def test_enrich_positions_handles_missing_timestamp():
    raw = [{"satlatitude": 10.0}]
    enriched = iss_service._enrich_positions(raw)
    assert "timestamp_ms" not in enriched[0]


# ── _utcnow / _age_seconds ────────────────────────────────────────────────────


def test_age_seconds_recent():
    now = iss_service._utcnow()
    assert iss_service._age_seconds(now) < 1.0


def test_age_seconds_old():
    old = iss_service._utcnow() - timedelta(hours=1)
    assert iss_service._age_seconds(old) >= 3600
