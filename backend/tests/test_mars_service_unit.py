"""Direct unit tests of mars_service for coverage of async internals."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import httpx
import pytest
import respx

from app.config import Settings
from app.models import MarsPhoto
from app.services import mars_service
from app.services.nasa_client import NasaClient, NasaClientError

_NASA_BASE = "https://api.nasa.example"


def _client() -> NasaClient:
    settings = Settings(  # type: ignore[call-arg]
        require_secrets=False,
        nasa_api_key="TEST",
        nasa_base_url=_NASA_BASE,
    )
    return NasaClient(settings)


@pytest.fixture
async def nasa():
    c = _client()
    try:
        yield c
    finally:
        await c.close()


def _photo(pid: int, rover: str = "curiosity", sol: int = 100, earth_date: str = "2020-01-01", camera: str = "FHAZ") -> dict:
    return {
        "id": pid,
        "sol": sol,
        "earth_date": earth_date,
        "img_src": f"https://mars.example/{pid}.jpg",
        "camera": {"name": camera},
        "rover": {"name": rover.capitalize()},
    }


# ── validate inputs ───────────────────────────────────────────────────────────


async def test_unknown_rover_raises(db_session, nasa):
    with pytest.raises(ValueError, match="Unknown rover"):
        await mars_service.fetch_photos(db_session, nasa, "marvin", sol=1)


async def test_no_sol_or_earth_date_raises(db_session, nasa):
    with pytest.raises(ValueError, match="sol or earth_date"):
        await mars_service.fetch_photos(db_session, nasa, "curiosity")


# ── cache miss ─────────────────────────────────────────────────────────────────


@respx.mock
async def test_cache_miss_sol(db_session, nasa):
    respx.get(f"{_NASA_BASE}/mars-photos/api/v1/rovers/curiosity/photos").mock(
        return_value=httpx.Response(200, json={"photos": [_photo(1, sol=200)]})
    )
    result = await mars_service.fetch_photos(db_session, nasa, "curiosity", sol=200)
    assert result.cached is False
    assert len(result.rows) == 1
    assert result.rows[0].sol == 200


@respx.mock
async def test_cache_miss_earth_date(db_session, nasa):
    respx.get(f"{_NASA_BASE}/mars-photos/api/v1/rovers/curiosity/photos").mock(
        return_value=httpx.Response(200, json={"photos": [_photo(2, earth_date="2020-02-01")]})
    )
    result = await mars_service.fetch_photos(db_session, nasa, "curiosity", earth_date="2020-02-01")
    assert result.cached is False
    assert result.rows[0].earth_date == "2020-02-01"


# ── cache hit ─────────────────────────────────────────────────────────────────


async def test_cache_hit_historical(db_session, nasa):
    db_session.add(
        MarsPhoto(
            id=10, sol=300, earth_date="2019-01-01",
            rover_name="curiosity", camera_name="FHAZ",
            img_src="x", fetched_at=datetime(2019, 1, 1, 0, 0, 0),
        )
    )
    await db_session.commit()

    with respx.mock:
        route = respx.get(f"{_NASA_BASE}/mars-photos/api/v1/rovers/curiosity/photos")
        result = await mars_service.fetch_photos(db_session, nasa, "curiosity", sol=300, camera="FHAZ")

    assert result.cached is True
    assert route.called is False


# ── stale fallback ─────────────────────────────────────────────────────────────


@respx.mock
async def test_stale_fallback(db_session, nasa):
    today = datetime.now(timezone.utc).date().isoformat()
    db_session.add(
        MarsPhoto(
            id=20, sol=400, earth_date=today,
            rover_name="curiosity", camera_name="FHAZ",
            img_src="x", fetched_at=datetime.utcnow() - timedelta(hours=1),
        )
    )
    await db_session.commit()

    respx.get(f"{_NASA_BASE}/mars-photos/api/v1/rovers/curiosity/photos").mock(
        return_value=httpx.Response(503)
    )
    result = await mars_service.fetch_photos(db_session, nasa, "curiosity", sol=400)
    assert result.stale is True
    assert result.is_today is True


@respx.mock
async def test_upstream_error_no_cache_raises(db_session, nasa):
    respx.get(f"{_NASA_BASE}/mars-photos/api/v1/rovers/curiosity/photos").mock(
        return_value=httpx.Response(503)
    )
    with pytest.raises(NasaClientError):
        await mars_service.fetch_photos(db_session, nasa, "curiosity", sol=500)


# ── upsert updates existing row ───────────────────────────────────────────────


@respx.mock
async def test_upsert_updates_existing(db_session, nasa):
    today = datetime.now(timezone.utc).date().isoformat()
    db_session.add(
        MarsPhoto(
            id=30, sol=600, earth_date=today,
            rover_name="curiosity", camera_name="FHAZ",
            img_src="old.jpg", fetched_at=datetime.utcnow() - timedelta(hours=6),
        )
    )
    await db_session.commit()

    respx.get(f"{_NASA_BASE}/mars-photos/api/v1/rovers/curiosity/photos").mock(
        return_value=httpx.Response(
            200,
            json={"photos": [_photo(30, sol=600, earth_date=today, camera="FHAZ")]},
        )
    )
    result = await mars_service.fetch_photos(db_session, nasa, "curiosity", sol=600)
    assert result.cached is False
    updated = await db_session.get(MarsPhoto, 30)
    assert updated is not None
    assert updated.img_src == "https://mars.example/30.jpg"


# ── today re-fetch: is_today computed from rows ───────────────────────────────


@respx.mock
async def test_is_today_set_when_earth_date_is_today(db_session, nasa):
    today = datetime.now(timezone.utc).date().isoformat()
    respx.get(f"{_NASA_BASE}/mars-photos/api/v1/rovers/perseverance/photos").mock(
        return_value=httpx.Response(
            200,
            json={"photos": [_photo(40, rover="perseverance", earth_date=today)]},
        )
    )
    result = await mars_service.fetch_photos(db_session, nasa, "perseverance", earth_date=today)
    assert result.is_today is True


# ── photo with no id is skipped ───────────────────────────────────────────────


@respx.mock
async def test_photo_without_id_skipped(db_session, nasa):
    respx.get(f"{_NASA_BASE}/mars-photos/api/v1/rovers/curiosity/photos").mock(
        return_value=httpx.Response(
            200,
            json={"photos": [{"sol": 1, "earth_date": "2020-01-01", "img_src": "x.jpg",
                               "camera": {"name": "FHAZ"}, "rover": {"name": "Curiosity"}}]},
        )
    )
    result = await mars_service.fetch_photos(db_session, nasa, "curiosity", sol=1)
    assert result.rows == []


# ── empty photos list ─────────────────────────────────────────────────────────


@respx.mock
async def test_empty_photos_list_no_is_today_when_not_today(db_session, nasa):
    respx.get(f"{_NASA_BASE}/mars-photos/api/v1/rovers/curiosity/photos").mock(
        return_value=httpx.Response(200, json={"photos": []})
    )
    result = await mars_service.fetch_photos(db_session, nasa, "curiosity", earth_date="2020-01-15")
    assert result.cached is False
    assert result.rows == []
    assert result.is_today is False


@respx.mock
async def test_empty_photos_list_is_today_when_today(db_session, nasa):
    today = datetime.now(timezone.utc).date().isoformat()
    respx.get(f"{_NASA_BASE}/mars-photos/api/v1/rovers/curiosity/photos").mock(
        return_value=httpx.Response(200, json={"photos": []})
    )
    result = await mars_service.fetch_photos(db_session, nasa, "curiosity", earth_date=today)
    assert result.is_today is True


# ── _latest_fetched_at edge case ──────────────────────────────────────────────


def test_latest_fetched_at_empty_returns_now():
    before = datetime.now(timezone.utc).replace(tzinfo=None)
    result = mars_service._latest_fetched_at([])
    after = datetime.now(timezone.utc).replace(tzinfo=None)
    assert before <= result <= after


# ── camera filter applied in params ──────────────────────────────────────────


@respx.mock
async def test_camera_param_sent_lowercase(db_session, nasa):
    route = respx.get(f"{_NASA_BASE}/mars-photos/api/v1/rovers/curiosity/photos").mock(
        return_value=httpx.Response(200, json={"photos": []})
    )
    await mars_service.fetch_photos(db_session, nasa, "curiosity", sol=9876, camera="FHAZ")
    assert route.called
    # camera should be sent lowercase per NASA API convention
    call_params = dict(route.calls[0].request.url.params)
    assert call_params.get("camera") == "fhaz"


# ── ROVER_CAMERAS / ROVERS constants ─────────────────────────────────────────


def test_rover_cameras_covers_all_rovers():
    for rover in mars_service.ROVERS:
        assert rover in mars_service.ROVER_CAMERAS
        assert len(mars_service.ROVER_CAMERAS[rover]) > 0


# ── MarsResult container ──────────────────────────────────────────────────────


def test_mars_result_fields():
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    r = mars_service.MarsResult(rows=[], cached=False, stale=True, is_today=True, fetched_at=now)
    assert r.stale is True
    assert r.is_today is True
