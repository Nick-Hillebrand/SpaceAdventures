"""Tests for sky-location: geocode_client, location_service, /api/v1/location
(20-location-and-sky-alerts.md — Foundation)."""

from __future__ import annotations

import httpx
import pytest
import respx
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.database import get_db
from app.main import create_app
from app.schemas.location import SetLocationRequest
from app.services import location_service
from app.services.geocode_client import GeocodeClient, GeocodeClientError
from app.services.ll2_client import LL2Client
from app.services.mars_raw_images_client import MarsRawImagesClient
from app.services.n2yo_client import N2YOClient
from app.services.nasa_client import NasaClient

_GEOCODE_BASE = "https://geocoding-api.open-meteo.example"

REGISTER_PAYLOAD = {
    "first_name": "Alice",
    "last_name": "Liddell",
    "email": "alice@example.com",
    "password": "securepassword",
    "consent_notifications": True,
}


async def _register_and_login(client, payload=REGISTER_PAYLOAD) -> tuple[int, dict]:
    r = await client.post("/api/v1/auth/register", json=payload)
    assert r.status_code == 201, r.text
    user_id = r.json()["id"]
    r2 = await client.post(
        "/api/v1/auth/login",
        json={"email_or_phone": payload["email"], "password": payload["password"]},
    )
    assert r2.status_code == 200, r2.text
    token = r2.json()["access_token"]
    return user_id, {"Authorization": f"Bearer {token}"}


def _geocode_results() -> list[dict]:
    return [
        {
            "name": "Paris",
            "country": "France",
            "admin1": "Ile-de-France",
            "latitude": 48.8566,
            "longitude": 2.3522,
            "timezone": "Europe/Paris",
        }
    ]


# ---------------------------------------------------------------------------
# geocode_client.py
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@respx.mock
async def test_geocode_client_search_success(settings):
    respx.get(f"{_GEOCODE_BASE}/v1/search").mock(
        return_value=httpx.Response(200, json={"results": _geocode_results()})
    )
    client = GeocodeClient(settings)
    try:
        results = await client.search("Paris")
        assert results[0]["name"] == "Paris"
    finally:
        await client.close()


@pytest.mark.asyncio
@respx.mock
async def test_geocode_client_connect_error(settings):
    respx.get(f"{_GEOCODE_BASE}/v1/search").mock(side_effect=httpx.ConnectError("boom"))
    client = GeocodeClient(settings)
    try:
        with pytest.raises(GeocodeClientError) as exc_info:
            await client.search("Paris")
        assert exc_info.value.code == "GEOCODE_UNAVAILABLE"
    finally:
        await client.close()


@pytest.mark.asyncio
@respx.mock
async def test_geocode_client_generic_http_error(settings):
    respx.get(f"{_GEOCODE_BASE}/v1/search").mock(side_effect=httpx.ReadTimeout("boom"))
    client = GeocodeClient(settings)
    try:
        with pytest.raises(GeocodeClientError) as exc_info:
            await client.search("Paris")
        assert exc_info.value.code == "GEOCODE_UNAVAILABLE"
    finally:
        await client.close()


@pytest.mark.asyncio
@respx.mock
async def test_geocode_client_5xx(settings):
    respx.get(f"{_GEOCODE_BASE}/v1/search").mock(return_value=httpx.Response(503))
    client = GeocodeClient(settings)
    try:
        with pytest.raises(GeocodeClientError) as exc_info:
            await client.search("Paris")
        assert exc_info.value.code == "GEOCODE_UNAVAILABLE"
    finally:
        await client.close()


@pytest.mark.asyncio
@respx.mock
async def test_geocode_client_4xx(settings):
    respx.get(f"{_GEOCODE_BASE}/v1/search").mock(return_value=httpx.Response(400))
    client = GeocodeClient(settings)
    try:
        with pytest.raises(GeocodeClientError) as exc_info:
            await client.search("Paris")
        assert exc_info.value.code == "GEOCODE_ERROR"
    finally:
        await client.close()


@pytest.mark.asyncio
@respx.mock
async def test_geocode_client_oversized_content_length(settings):
    respx.get(f"{_GEOCODE_BASE}/v1/search").mock(
        return_value=httpx.Response(
            200,
            json={"results": _geocode_results()},
            headers={"content-length": str(6 * 1024 * 1024)},
        )
    )
    client = GeocodeClient(settings)
    try:
        with pytest.raises(GeocodeClientError) as exc_info:
            await client.search("Paris")
        assert exc_info.value.code == "GEOCODE_ERROR"
    finally:
        await client.close()


@pytest.mark.asyncio
@respx.mock
async def test_geocode_client_invalid_json(settings):
    respx.get(f"{_GEOCODE_BASE}/v1/search").mock(
        return_value=httpx.Response(200, content=b"not json", headers={"content-type": "text/plain"})
    )
    client = GeocodeClient(settings)
    try:
        with pytest.raises(GeocodeClientError) as exc_info:
            await client.search("Paris")
        assert exc_info.value.code == "GEOCODE_ERROR"
    finally:
        await client.close()


@pytest.mark.asyncio
@respx.mock
async def test_geocode_client_no_results(settings):
    respx.get(f"{_GEOCODE_BASE}/v1/search").mock(return_value=httpx.Response(200, json={"results": []}))
    client = GeocodeClient(settings)
    try:
        with pytest.raises(GeocodeClientError) as exc_info:
            await client.search("Nowhereville")
        assert exc_info.value.code == "GEOCODE_NO_RESULT"
        assert exc_info.value.status_code == 404
    finally:
        await client.close()


# ---------------------------------------------------------------------------
# location_service.py — search_location (untrusted-shape filtering, rule 9)
# ---------------------------------------------------------------------------


class _FakeGeocodeClient:
    def __init__(self, results: list[dict]) -> None:
        self._results = results

    async def search(self, query: str, count: int = 5) -> list[dict]:
        return self._results


@pytest.mark.asyncio
async def test_search_location_filters_malformed_candidates():
    results = [
        _geocode_results()[0],
        {"name": "Missing coords", "country": "X"},  # no latitude/longitude — skipped
        {"name": "Bad lat", "latitude": "not-a-number", "longitude": 1.0},  # skipped
    ]
    candidates = await location_service.search_location(_FakeGeocodeClient(results), "Paris")
    assert len(candidates) == 1
    assert candidates[0].name == "Paris"


@pytest.mark.asyncio
async def test_search_location_defaults_missing_timezone_to_utc():
    results = [{"name": "Nowhere", "latitude": 0.0, "longitude": 0.0}]
    candidates = await location_service.search_location(_FakeGeocodeClient(results), "Nowhere")
    assert candidates[0].timezone == "UTC"


@pytest.mark.asyncio
async def test_search_location_caps_at_max_candidates():
    results = [dict(_geocode_results()[0], name=f"Place {i}") for i in range(10)]
    candidates = await location_service.search_location(_FakeGeocodeClient(results), "Place")
    assert len(candidates) == location_service.MAX_CANDIDATES


def test_geocode_error_response_maps_status_and_code():
    exc = GeocodeClientError("GEOCODE_NO_RESULT", "No matching location found", 404)
    http_exc = location_service.geocode_error_response(exc)
    assert http_exc.status_code == 404
    assert http_exc.detail["error"]["code"] == "GEOCODE_NO_RESULT"


# ---------------------------------------------------------------------------
# location_service.py — set_location / clear_location
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_set_location_rounds_and_persists(db_session):
    from app.models.user import User
    from passlib.context import CryptContext

    pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")
    user = User(
        first_name="Alice", last_name="Test", email="a@example.com",
        password_hash=pwd_ctx.hash("pw"),
    )
    db_session.add(user)
    await db_session.flush()

    data = SetLocationRequest(
        name="Paris", latitude=48.856614, longitude=2.352222, timezone="Europe/Paris"
    )
    updated = await location_service.set_location(db_session, user, data)
    assert updated.location_lat == 48.86
    assert updated.location_lng == 2.35
    assert updated.location_name == "Paris"
    assert updated.location_tz == "Europe/Paris"


@pytest.mark.asyncio
async def test_set_location_rejects_out_of_range_latitude(db_session):
    from app.models.user import User
    from fastapi import HTTPException
    from passlib.context import CryptContext

    pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")
    user = User(
        first_name="Alice", last_name="Test", email="a@example.com",
        password_hash=pwd_ctx.hash("pw"),
    )
    db_session.add(user)
    await db_session.flush()

    data = SetLocationRequest(name="Nowhere", latitude=91.0, longitude=0.0, timezone="UTC")
    with pytest.raises(HTTPException) as exc_info:
        await location_service.set_location(db_session, user, data)
    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_set_location_rejects_out_of_range_longitude(db_session):
    from app.models.user import User
    from fastapi import HTTPException
    from passlib.context import CryptContext

    pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")
    user = User(
        first_name="Alice", last_name="Test", email="a@example.com",
        password_hash=pwd_ctx.hash("pw"),
    )
    db_session.add(user)
    await db_session.flush()

    data = SetLocationRequest(name="Nowhere", latitude=0.0, longitude=181.0, timezone="UTC")
    with pytest.raises(HTTPException) as exc_info:
        await location_service.set_location(db_session, user, data)
    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_clear_location_nulls_all_columns(db_session):
    from app.models.user import User
    from passlib.context import CryptContext

    pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")
    user = User(
        first_name="Alice", last_name="Test", email="a@example.com",
        password_hash=pwd_ctx.hash("pw"),
        location_name="Paris", location_lat=48.86, location_lng=2.35, location_tz="Europe/Paris",
    )
    db_session.add(user)
    await db_session.flush()

    cleared = await location_service.clear_location(db_session, user)
    assert cleared.location_name is None
    assert cleared.location_lat is None
    assert cleared.location_lng is None
    assert cleared.location_tz is None


# ---------------------------------------------------------------------------
# /api/v1/location — router integration
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@respx.mock
async def test_search_location_route_success(client):
    _, headers = await _register_and_login(client)
    respx.get(f"{_GEOCODE_BASE}/v1/search").mock(
        return_value=httpx.Response(200, json={"results": _geocode_results()})
    )
    r = await client.get("/api/v1/location/search", params={"q": "Paris"}, headers=headers)
    assert r.status_code == 200
    body = r.json()
    assert body["candidates"][0]["name"] == "Paris"


@pytest.mark.asyncio
async def test_search_location_route_unauthenticated(client):
    r = await client.get("/api/v1/location/search", params={"q": "Paris"})
    assert r.status_code == 401


@pytest.mark.asyncio
@respx.mock
async def test_search_location_route_no_result(client):
    _, headers = await _register_and_login(client)
    respx.get(f"{_GEOCODE_BASE}/v1/search").mock(return_value=httpx.Response(200, json={"results": []}))
    r = await client.get("/api/v1/location/search", params={"q": "Nowhereville"}, headers=headers)
    assert r.status_code == 404
    assert r.json()["detail"]["error"]["code"] == "GEOCODE_NO_RESULT"


@pytest.mark.asyncio
@respx.mock
async def test_search_location_route_rate_limited(client, settings):
    from app.rate_limit import GEOCODE_LIMIT

    _, headers = await _register_and_login(client)
    respx.get(f"{_GEOCODE_BASE}/v1/search").mock(
        return_value=httpx.Response(200, json={"results": _geocode_results()})
    )
    for _ in range(GEOCODE_LIMIT):
        r = await client.get("/api/v1/location/search", params={"q": "Paris"}, headers=headers)
        assert r.status_code == 200
    r = await client.get("/api/v1/location/search", params={"q": "Paris"}, headers=headers)
    assert r.status_code == 429


@pytest.mark.asyncio
async def test_set_location_route(client):
    _, headers = await _register_and_login(client)
    r = await client.post(
        "/api/v1/location",
        json={"name": "Paris", "latitude": 48.8566, "longitude": 2.3522, "timezone": "Europe/Paris"},
        headers=headers,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["location_name"] == "Paris"
    assert body["location_lat"] == 48.86


@pytest.mark.asyncio
async def test_set_location_route_invalid_coordinates(client):
    _, headers = await _register_and_login(client)
    r = await client.post(
        "/api/v1/location",
        json={"name": "Nowhere", "latitude": 999.0, "longitude": 0.0, "timezone": "UTC"},
        headers=headers,
    )
    assert r.status_code == 400


async def _make_client_without_geocode(db_engine, settings) -> AsyncClient:
    """Mirror conftest.py's `client` fixture but skip wiring `geocode_client`
    onto app.state, so `_get_geocode_client`'s 503 defensive branch (deploy
    misconfiguration) can be exercised."""
    factory = async_sessionmaker(db_engine, expire_on_commit=False, class_=AsyncSession)

    async def _override_get_db():
        async with factory() as session:
            yield session

    app = create_app(settings=settings)
    app.state.nasa_client = NasaClient(settings)
    app.state.n2yo_client = N2YOClient(settings)
    app.state.ll2_client = LL2Client(settings)
    app.state.mars_raw_images_client = MarsRawImagesClient(settings)
    app.dependency_overrides[get_db] = _override_get_db

    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


@pytest.mark.asyncio
async def test_search_location_route_geocode_client_not_initialised(db_engine, settings):
    client = await _make_client_without_geocode(db_engine, settings)
    try:
        _, headers = await _register_and_login(client)
        r = await client.get("/api/v1/location/search", params={"q": "Paris"}, headers=headers)
        assert r.status_code == 503
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_clear_location_route(client):
    _, headers = await _register_and_login(client)
    await client.post(
        "/api/v1/location",
        json={"name": "Paris", "latitude": 48.8566, "longitude": 2.3522, "timezone": "Europe/Paris"},
        headers=headers,
    )
    r = await client.delete("/api/v1/location", headers=headers)
    assert r.status_code == 204

    me = await client.get("/api/v1/auth/me", headers=headers)
    assert me.json()["location_name"] is None
