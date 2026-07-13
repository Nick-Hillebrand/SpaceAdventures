"""ISS route integration tests."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import httpx
import respx

from app.models import IssPassSet, IssPositionBatch, IssTle, N2yoQuota

_N2YO_BASE = "https://api.n2yo.example/rest/v1/satellite"

_POSITION = {
    "satlatitude": 51.5,
    "satlongitude": -0.1,
    "sataltitude": 422.6,
    "azimuth": 300.5,
    "elevation": 25.3,
    "ra": 87.6,
    "dec": -10.2,
    "timestamp": 1_700_000_000,
    "eclipsed": False,
}

_PASS = {
    "startUTC": 1_700_001_000,
    "maxUTC": 1_700_001_060,
    "endUTC": 1_700_001_120,
    "startAzCompass": "W",
    "endAzCompass": "E",
    "maxEl": 45.2,
    "mag": -3.0,
    "duration": 120,
}

_TLE_RAW = "ISS (ZARYA)\\n1 25544U 98067A   21001.50000000  .00001234  00000-0  00000-0 0  9999\\n2 25544  51.6435 000.0000 0001234  00.0000 000.0000 15.48999999999999"


def _positions_payload() -> dict:
    return {
        "info": {"satname": "ISS", "satid": 25544, "transactionscount": 1},
        "positions": [dict(_POSITION)] * 300,
    }


def _tle_payload() -> dict:
    return {
        "info": {"satname": "ISS", "satid": 25544, "transactionscount": 1},
        "tle": _TLE_RAW,
    }


def _passes_payload() -> dict:
    return {
        "info": {"satname": "ISS", "satid": 25544, "transactionscount": 1},
        "passes": [dict(_PASS)],
    }


# ── positions ─────────────────────────────────────────────────────────────────


@respx.mock
async def test_get_positions_live(client):
    respx.get(f"{_N2YO_BASE}/positions/25544/0.0/0.0/0.0/300").mock(
        return_value=httpx.Response(200, json=_positions_payload())
    )
    response = await client.get("/api/v1/iss/positions")
    assert response.status_code == 200
    body = response.json()
    assert body["cached"] is False
    assert body["quota_exhausted"] is False
    assert len(body["positions"]) == 300
    # timestamp_ms must be added (P11)
    pos = body["positions"][0]
    assert pos["timestamp_ms"] == _POSITION["timestamp"] * 1000


@respx.mock
async def test_get_positions_cached(client, db_session):
    positions = [{"timestamp_ms": 1_700_000_000_000, "satlatitude": 10.0}]
    db_session.add(
        IssPositionBatch(
            id=1,
            positions=positions,
            fetched_at=datetime.utcnow(),  # just now → still within TTL
        )
    )
    await db_session.commit()

    route = respx.get(f"{_N2YO_BASE}/positions/25544/0.0/0.0/0.0/300")
    response = await client.get("/api/v1/iss/positions")
    assert response.status_code == 200
    assert response.json()["cached"] is True
    assert not route.called


@respx.mock
async def test_get_positions_quota_exhausted_with_cache(client, db_session):
    positions = [{"timestamp_ms": 1_700_000_000_000}]
    db_session.add(
        IssPositionBatch(
            id=1,
            positions=positions,
            fetched_at=datetime.utcnow() - timedelta(minutes=10),  # stale
        )
    )
    db_session.add(
        N2yoQuota(
            id=1,
            window_start=datetime.utcnow(),
            used=900,
        )
    )
    await db_session.commit()

    response = await client.get("/api/v1/iss/positions")
    assert response.status_code == 200
    assert response.json()["quota_exhausted"] is True
    assert response.json()["cached"] is True


@respx.mock
async def test_get_positions_quota_exhausted_no_cache(client, db_session):
    db_session.add(
        N2yoQuota(id=1, window_start=datetime.utcnow(), used=900)
    )
    await db_session.commit()

    response = await client.get("/api/v1/iss/positions")
    assert response.status_code == 429
    assert response.json()["detail"]["error"]["code"] == "N2YO_QUOTA_EXHAUSTED"


@respx.mock
async def test_get_positions_n2yo_error(client):
    respx.get(f"{_N2YO_BASE}/positions/25544/0.0/0.0/0.0/300").mock(
        return_value=httpx.Response(200, json={"error": "Bad API key"})
    )
    response = await client.get("/api/v1/iss/positions")
    assert response.status_code == 502


# ── TLE ───────────────────────────────────────────────────────────────────────


@respx.mock
async def test_get_tle_live(client):
    respx.get(f"{_N2YO_BASE}/tle/25544").mock(
        return_value=httpx.Response(200, json=_tle_payload())
    )
    response = await client.get("/api/v1/iss/tle")
    assert response.status_code == 200
    body = response.json()
    assert body["cached"] is False
    assert "25544" in body["tle_line1"]


@respx.mock
async def test_get_tle_cached(client, db_session):
    db_session.add(
        IssTle(
            id=1,
            tle_line0="ISS",
            tle_line1="line1",
            tle_line2="line2",
            fetched_at=datetime.utcnow(),
        )
    )
    await db_session.commit()

    route = respx.get(f"{_N2YO_BASE}/tle/25544")
    response = await client.get("/api/v1/iss/tle")
    assert response.status_code == 200
    assert response.json()["cached"] is True
    assert not route.called


@respx.mock
async def test_get_tle_quota_exhausted_no_cache(client, db_session):
    db_session.add(N2yoQuota(id=1, window_start=datetime.utcnow(), used=900))
    await db_session.commit()

    response = await client.get("/api/v1/iss/tle")
    assert response.status_code == 429


@respx.mock
async def test_get_tle_quota_exhausted_serves_stale(client, db_session):
    db_session.add(
        IssTle(id=1, tle_line0="ISS", tle_line1="L1", tle_line2="L2",
               fetched_at=datetime.utcnow() - timedelta(hours=12))
    )
    db_session.add(N2yoQuota(id=1, window_start=datetime.utcnow(), used=900))
    await db_session.commit()

    response = await client.get("/api/v1/iss/tle")
    assert response.status_code == 200
    body = response.json()
    assert body["quota_exhausted"] is True
    assert body["cached"] is True


# ── passes ────────────────────────────────────────────────────────────────────


@respx.mock
async def test_get_visual_passes_live(client):
    respx.get(f"{_N2YO_BASE}/visualpasses/25544/51.5/-0.1/30.0/7/10").mock(
        return_value=httpx.Response(200, json=_passes_payload())
    )
    response = await client.get("/api/v1/iss/passes/visual", params={"lat": 51.5, "lng": -0.1, "alt": 30.0})
    assert response.status_code == 200
    body = response.json()
    assert body["cached"] is False
    assert len(body["passes"]) == 1


@respx.mock
async def test_get_radio_passes_live(client):
    respx.get(f"{_N2YO_BASE}/radiopasses/25544/51.5/-0.1/30.0/7/10").mock(
        return_value=httpx.Response(200, json=_passes_payload())
    )
    response = await client.get("/api/v1/iss/passes/radio", params={"lat": 51.5, "lng": -0.1, "alt": 30.0})
    assert response.status_code == 200
    assert response.json()["cached"] is False


@respx.mock
async def test_get_radio_passes_computes_missing_duration(client):
    """N2YO's real radiopasses endpoint never returns a `duration` field."""
    radio_pass = {k: v for k, v in _PASS.items() if k != "duration"}
    respx.get(f"{_N2YO_BASE}/radiopasses/25544/51.5/-0.1/30.0/7/10").mock(
        return_value=httpx.Response(
            200,
            json={
                "info": {"satname": "ISS", "satid": 25544, "transactionscount": 1},
                "passes": [radio_pass],
            },
        )
    )
    response = await client.get("/api/v1/iss/passes/radio", params={"lat": 51.5, "lng": -0.1, "alt": 30.0})
    assert response.status_code == 200
    body = response.json()["passes"][0]
    assert body["duration"] == radio_pass["endUTC"] - radio_pass["startUTC"]


@respx.mock
async def test_get_passes_cached(client, db_session):
    db_session.add(
        IssPassSet(
            pass_type="visual",
            observer_lat=51.5,
            observer_lng=-0.1,
            observer_alt=30.0,
            passes_json=[_PASS],
            fetched_at=datetime.utcnow(),
        )
    )
    await db_session.commit()

    route = respx.get(f"{_N2YO_BASE}/visualpasses/25544/51.5/-0.1/30.0/7/10")
    response = await client.get("/api/v1/iss/passes/visual", params={"lat": 51.5, "lng": -0.1, "alt": 30.0})
    assert response.status_code == 200
    assert response.json()["cached"] is True
    assert not route.called


@respx.mock
async def test_get_passes_quota_exhausted_no_cache(client, db_session):
    db_session.add(N2yoQuota(id=1, window_start=datetime.utcnow(), used=900))
    await db_session.commit()

    response = await client.get("/api/v1/iss/passes/visual", params={"lat": 0.0, "lng": 0.0, "alt": 0.0})
    assert response.status_code == 429


# ── parameter validation ──────────────────────────────────────────────────────


async def test_passes_invalid_lat(client):
    response = await client.get("/api/v1/iss/passes/visual", params={"lat": 95.0, "lng": 0.0, "alt": 0.0})
    assert response.status_code == 400
    assert response.json()["detail"]["error"]["code"] == "INVALID_PARAMS"


async def test_passes_invalid_lng(client):
    response = await client.get("/api/v1/iss/passes/radio", params={"lat": 0.0, "lng": 200.0, "alt": 0.0})
    assert response.status_code == 400


async def test_passes_invalid_alt(client):
    response = await client.get("/api/v1/iss/passes/visual", params={"lat": 0.0, "lng": 0.0, "alt": 15000.0})
    assert response.status_code == 400


# ── quota endpoint ────────────────────────────────────────────────────────────


async def test_get_quota(client, db_session):
    db_session.add(
        N2yoQuota(id=1, window_start=datetime.utcnow() - timedelta(minutes=30), used=42)
    )
    await db_session.commit()

    response = await client.get("/api/v1/iss/quota")
    assert response.status_code == 200
    body = response.json()
    assert body["used"] == 42
    assert body["cap"] == 900
    assert "window_start" in body
    assert "resets_at" in body


async def test_get_quota_creates_row_if_missing(client):
    response = await client.get("/api/v1/iss/quota")
    assert response.status_code == 200
    assert response.json()["used"] == 0


# ── N2YO error body (P12) ─────────────────────────────────────────────────────


@respx.mock
async def test_n2yo_error_in_body_returns_502(client):
    respx.get(f"{_N2YO_BASE}/tle/25544").mock(
        return_value=httpx.Response(200, json={"error": "Invalid API key"})
    )
    response = await client.get("/api/v1/iss/tle")
    assert response.status_code == 502
    assert response.json()["detail"]["error"]["code"] == "N2YO_ERROR"


# ── Router N2YOError exception handler coverage ───────────────────────────────


@respx.mock
async def test_positions_n2yo_error_hits_router_handler(client):
    """N2YOError from positions service propagates to router except block."""
    respx.get(f"{_N2YO_BASE}/positions/25544/0.0/0.0/0.0/300").mock(
        return_value=httpx.Response(200, json={"error": "Bad API key"})
    )
    response = await client.get("/api/v1/iss/positions")
    assert response.status_code == 502
    body = response.json()
    assert body["detail"]["error"]["code"] == "N2YO_ERROR"


@respx.mock
async def test_visual_passes_n2yo_error_hits_router_handler(client):
    """N2YOError from visual passes service propagates to router except block."""
    respx.get(f"{_N2YO_BASE}/visualpasses/25544/0.0/0.0/0.0/7/10").mock(
        return_value=httpx.Response(200, json={"error": "Quota exceeded"})
    )
    response = await client.get(
        "/api/v1/iss/passes/visual", params={"lat": 0.0, "lng": 0.0, "alt": 0.0}
    )
    assert response.status_code == 502
    body = response.json()
    assert body["detail"]["error"]["code"] == "N2YO_ERROR"


@respx.mock
async def test_radio_passes_n2yo_error_hits_router_handler(client):
    """N2YOError from radio passes service propagates to router except block."""
    respx.get(f"{_N2YO_BASE}/radiopasses/25544/0.0/0.0/0.0/7/10").mock(
        return_value=httpx.Response(200, json={"error": "Quota exceeded"})
    )
    response = await client.get(
        "/api/v1/iss/passes/radio", params={"lat": 0.0, "lng": 0.0, "alt": 0.0}
    )
    assert response.status_code == 502
    body = response.json()
    assert body["detail"]["error"]["code"] == "N2YO_ERROR"


async def test_n2yo_client_not_initialized_returns_503(db_engine, settings):
    """_get_n2yo_client raises 503 when n2yo_client is missing from app state."""
    from httpx import ASGITransport, AsyncClient as httpxAsyncClient
    from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession

    from app.database import get_db
    from app.main import create_app
    from app.services.nasa_client import NasaClient
    from app.services.ll2_client import LL2Client

    factory = async_sessionmaker(db_engine, expire_on_commit=False, class_=AsyncSession)

    async def _override_get_db():
        async with factory() as session:
            yield session

    no_n2yo_app = create_app(settings=settings)
    no_n2yo_app.state.nasa_client = NasaClient(settings)
    no_n2yo_app.state.ll2_client = LL2Client(settings)
    # Intentionally do NOT set n2yo_client
    no_n2yo_app.dependency_overrides[get_db] = _override_get_db

    transport = ASGITransport(app=no_n2yo_app)
    async with httpxAsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get("/api/v1/iss/positions")
    assert response.status_code == 503

    await no_n2yo_app.state.nasa_client.close()
    await no_n2yo_app.state.ll2_client.close()
