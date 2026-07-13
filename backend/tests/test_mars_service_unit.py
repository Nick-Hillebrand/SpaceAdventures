"""Direct unit tests of mars_service for coverage of async internals."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import httpx
import pytest
import respx

from app.config import Settings
from app.models import MarsPhoto
from app.services import mars_service
from app.services.mars_raw_images_client import MarsRawImagesClient
from app.services.nasa_client import NasaClientError

MSL_BASE = "https://mars.nasa.gov/api/v1/raw_image_items/"
M20_BASE = "https://mars.nasa.gov/rss/api/"


def _client() -> MarsRawImagesClient:
    settings = Settings(require_secrets=False)  # type: ignore[call-arg]
    return MarsRawImagesClient(settings)


@pytest.fixture
async def mars_client():
    c = _client()
    try:
        yield c
    finally:
        await c.close()


def _msl_item(item_id: int, sol: int = 100, date_taken: str = "2020-01-01T00:00:00Z", instrument: str = "FHAZ_LEFT_A") -> dict:
    return {
        "id": item_id,
        "sol": sol,
        "date_taken": date_taken,
        "instrument": instrument,
        "https_url": f"https://mars.nasa.gov/{item_id}.jpg",
    }


def _msl_payload(*items: dict, more: bool = False) -> dict:
    return {"items": list(items), "more": more, "total": len(items)}


def _m20_image(image_id: str, sol: int = 100, date_taken: str = "2021-03-01T00:00:00Z", instrument: str = "NAVCAM_LEFT") -> dict:
    return {
        "imageid": image_id,
        "sol": sol,
        "date_taken_utc": date_taken,
        "camera": {"instrument": instrument},
        "image_files": {"full_res": f"https://mars.nasa.gov/{image_id}.jpg"},
    }


def _m20_payload(*images: dict) -> dict:
    return {"images": list(images), "num_images": len(images)}


# ── validate inputs ───────────────────────────────────────────────────────────


async def test_unknown_rover_raises(db_session, mars_client):
    with pytest.raises(ValueError, match="Unknown rover"):
        await mars_service.fetch_photos(db_session, mars_client, "marvin", sol=1)


async def test_no_sol_or_earth_date_raises(db_session, mars_client):
    with pytest.raises(ValueError, match="sol or earth_date"):
        await mars_service.fetch_photos(db_session, mars_client, "curiosity")


# ── cache miss ─────────────────────────────────────────────────────────────────


@respx.mock
async def test_cache_miss_sol(db_session, mars_client):
    respx.get(MSL_BASE).mock(
        return_value=httpx.Response(200, json=_msl_payload(_msl_item(1, sol=200)))
    )
    result = await mars_service.fetch_photos(db_session, mars_client, "curiosity", sol=200)
    assert result.cached is False
    assert len(result.rows) == 1
    assert result.rows[0].sol == 200
    assert result.rows[0].camera_name == "FHAZ"


@respx.mock
async def test_cache_miss_earth_date(db_session, mars_client):
    # earth_date-only queries fan out across sol-1/sol/sol+1 candidates
    respx.get(MSL_BASE).mock(
        return_value=httpx.Response(
            200, json=_msl_payload(_msl_item(2, date_taken="2020-02-01T00:00:00Z"))
        )
    )
    result = await mars_service.fetch_photos(
        db_session, mars_client, "curiosity", earth_date="2020-02-01"
    )
    assert result.cached is False
    assert result.rows[0].earth_date == "2020-02-01"


# ── cache hit ─────────────────────────────────────────────────────────────────


async def test_cache_hit_historical(db_session, mars_client):
    db_session.add(
        MarsPhoto(
            id=10, sol=300, earth_date="2019-01-01",
            rover_name="curiosity", camera_name="FHAZ",
            img_src="x", fetched_at=datetime(2019, 1, 1, 0, 0, 0),
        )
    )
    await db_session.commit()

    with respx.mock:
        route = respx.get(MSL_BASE)
        result = await mars_service.fetch_photos(
            db_session, mars_client, "curiosity", sol=300, camera="FHAZ"
        )

    assert result.cached is True
    assert route.called is False


# ── stale fallback ─────────────────────────────────────────────────────────────


@respx.mock
async def test_stale_fallback(db_session, mars_client):
    today = datetime.now(timezone.utc).date().isoformat()
    db_session.add(
        MarsPhoto(
            id=20, sol=400, earth_date=today,
            rover_name="curiosity", camera_name="FHAZ",
            img_src="x", fetched_at=datetime.utcnow() - timedelta(hours=1),
        )
    )
    await db_session.commit()

    respx.get(MSL_BASE).mock(return_value=httpx.Response(503))
    result = await mars_service.fetch_photos(db_session, mars_client, "curiosity", sol=400)
    assert result.stale is True
    assert result.is_today is True


@respx.mock
async def test_upstream_error_no_cache_raises(db_session, mars_client):
    respx.get(MSL_BASE).mock(return_value=httpx.Response(503))
    with pytest.raises(NasaClientError):
        await mars_service.fetch_photos(db_session, mars_client, "curiosity", sol=500)


# ── upsert updates existing row ───────────────────────────────────────────────


@respx.mock
async def test_upsert_updates_existing(db_session, mars_client):
    today = datetime.now(timezone.utc).date().isoformat()
    db_session.add(
        MarsPhoto(
            id=30, sol=600, earth_date=today,
            rover_name="curiosity", camera_name="FHAZ",
            img_src="old.jpg", fetched_at=datetime.utcnow() - timedelta(hours=6),
        )
    )
    await db_session.commit()

    respx.get(MSL_BASE).mock(
        return_value=httpx.Response(
            200,
            json=_msl_payload(_msl_item(30, sol=600, date_taken=f"{today}T00:00:00Z")),
        )
    )
    result = await mars_service.fetch_photos(db_session, mars_client, "curiosity", sol=600)
    assert result.cached is False
    updated = await db_session.get(MarsPhoto, 30)
    assert updated is not None
    assert updated.img_src == "https://mars.nasa.gov/30.jpg"


# ── today re-fetch: is_today computed from rows ───────────────────────────────


@respx.mock
async def test_is_today_set_when_earth_date_is_today(db_session, mars_client):
    today = datetime.now(timezone.utc).date().isoformat()
    respx.get(M20_BASE).mock(
        return_value=httpx.Response(
            200,
            json=_m20_payload(_m20_image("IMG1", date_taken=f"{today}T00:00:00Z")),
        )
    )
    result = await mars_service.fetch_photos(
        db_session, mars_client, "perseverance", earth_date=today
    )
    assert result.is_today is True


# ── photo with no id is skipped ───────────────────────────────────────────────


@respx.mock
async def test_photo_without_id_skipped(db_session, mars_client):
    respx.get(MSL_BASE).mock(
        return_value=httpx.Response(
            200,
            json={"items": [{"sol": 1, "date_taken": "2020-01-01T00:00:00Z", "instrument": "FHAZ_LEFT_A"}], "more": False},
        )
    )
    result = await mars_service.fetch_photos(db_session, mars_client, "curiosity", sol=1)
    assert result.rows == []


# ── empty photos list ─────────────────────────────────────────────────────────


@respx.mock
async def test_empty_photos_list_no_is_today_when_not_today(db_session, mars_client):
    respx.get(MSL_BASE).mock(return_value=httpx.Response(200, json=_msl_payload()))
    result = await mars_service.fetch_photos(
        db_session, mars_client, "curiosity", earth_date="2020-01-15"
    )
    assert result.cached is False
    assert result.rows == []
    assert result.is_today is False


@respx.mock
async def test_empty_photos_list_is_today_when_today(db_session, mars_client):
    today = datetime.now(timezone.utc).date().isoformat()
    respx.get(MSL_BASE).mock(return_value=httpx.Response(200, json=_msl_payload()))
    result = await mars_service.fetch_photos(db_session, mars_client, "curiosity", earth_date=today)
    assert result.is_today is True


# ── _latest_fetched_at edge case ──────────────────────────────────────────────


def test_latest_fetched_at_empty_returns_now():
    before = datetime.now(timezone.utc)
    result = mars_service._latest_fetched_at([])
    after = datetime.now(timezone.utc)
    assert before <= result <= after


# ── camera filter applied client-side ─────────────────────────────────────────


@respx.mock
async def test_camera_filter_normalizes_msl_instrument(db_session, mars_client):
    route = respx.get(MSL_BASE).mock(
        return_value=httpx.Response(
            200,
            json=_msl_payload(
                _msl_item(40, sol=9876, instrument="FHAZ_LEFT_A"),
                _msl_item(41, sol=9876, instrument="MAST_LEFT"),
            ),
        )
    )
    result = await mars_service.fetch_photos(
        db_session, mars_client, "curiosity", sol=9876, camera="FHAZ"
    )
    assert route.called
    assert len(result.rows) == 1
    assert result.rows[0].camera_name == "FHAZ"


# ── no live source rovers ─────────────────────────────────────────────────────


async def test_opportunity_raises_no_live_source_without_cache(db_session, mars_client):
    with pytest.raises(NasaClientError) as exc:
        await mars_service.fetch_photos(db_session, mars_client, "opportunity", sol=1)
    assert exc.value.code == "MARS_NO_LIVE_SOURCE"


async def test_spirit_serves_cache_without_attempting_live_fetch(db_session, mars_client):
    db_session.add(
        MarsPhoto(
            id=50, sol=1, earth_date="2005-01-01",
            rover_name="spirit", camera_name="PANCAM",
            img_src="x", fetched_at=datetime(2005, 1, 1, 0, 0, 0),
        )
    )
    await db_session.commit()

    with respx.mock:
        result = await mars_service.fetch_photos(db_session, mars_client, "spirit", sol=1)

    assert result.cached is True
    assert len(result.rows) == 1


# ── ROVER_CAMERAS / ROVERS constants ─────────────────────────────────────────


def test_rover_cameras_covers_all_rovers():
    for rover in mars_service.ROVERS:
        assert rover in mars_service.ROVER_CAMERAS
        assert len(mars_service.ROVER_CAMERAS[rover]) > 0


def test_perseverance_cameras_include_supercam():
    assert "SUPERCAM_RMI" in mars_service.ROVER_CAMERAS["perseverance"]


# ── MarsResult container ──────────────────────────────────────────────────────


def test_mars_result_fields():
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    r = mars_service.MarsResult(rows=[], cached=False, stale=True, is_today=True, fetched_at=now)
    assert r.stale is True
    assert r.is_today is True
