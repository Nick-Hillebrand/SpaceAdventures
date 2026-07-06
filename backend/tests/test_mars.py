from __future__ import annotations

from datetime import datetime, timedelta, timezone

import httpx
import pytest
import respx
from sqlalchemy import select

from app.models import MarsPhoto

_NASA_PHOTOS_BASE = "https://api.nasa.example/mars-photos/api/v1/rovers"


def _photo(
    photo_id: int,
    rover: str = "curiosity",
    sol: int = 1000,
    earth_date: str = "2020-01-01",
    camera: str = "FHAZ",
) -> dict:
    return {
        "id": photo_id,
        "sol": sol,
        "earth_date": earth_date,
        "img_src": f"https://mars.example/{photo_id}.jpg",
        "camera": {"name": camera, "full_name": camera},
        "rover": {"name": rover.capitalize(), "landing_date": "2012-08-06"},
    }


def _photos_response(*photos: dict) -> dict:
    return {"photos": list(photos)}


# ── /rovers ───────────────────────────────────────────────────────────────────


async def test_get_rovers(client):
    response = await client.get("/api/v1/mars/rovers")
    assert response.status_code == 200
    body = response.json()
    names = [r["name"] for r in body["data"]]
    assert "curiosity" in names
    assert "perseverance" in names
    assert "opportunity" in names
    assert "spirit" in names
    # Cameras list populated for curiosity
    curiosity = next(r for r in body["data"] if r["name"] == "curiosity")
    assert "FHAZ" in curiosity["cameras"]


# ── cache miss (sol) ──────────────────────────────────────────────────────────


@respx.mock
async def test_get_photos_by_sol_cache_miss(client, db_session):
    respx.get(f"{_NASA_PHOTOS_BASE}/curiosity/photos").mock(
        return_value=httpx.Response(
            200, json=_photos_response(_photo(1, sol=1000, earth_date="2020-01-01"))
        )
    )

    response = await client.get(
        "/api/v1/mars/photos",
        params={"rover": "curiosity", "sol": 1000},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["cached"] is False
    assert body["stale"] is False
    assert body["is_today"] is False
    assert len(body["data"]) == 1
    assert body["data"][0]["id"] == 1

    rows = (await db_session.execute(select(MarsPhoto))).scalars().all()
    assert len(rows) == 1


# ── cache miss (earth_date) ───────────────────────────────────────────────────


@respx.mock
async def test_get_photos_by_earth_date_cache_miss(client, db_session):
    respx.get(f"{_NASA_PHOTOS_BASE}/curiosity/photos").mock(
        return_value=httpx.Response(
            200, json=_photos_response(_photo(2, earth_date="2020-03-15"))
        )
    )

    response = await client.get(
        "/api/v1/mars/photos",
        params={"rover": "curiosity", "earth_date": "2020-03-15"},
    )
    assert response.status_code == 200
    assert response.json()["cached"] is False


# ── cache hit (historical) ────────────────────────────────────────────────────


@respx.mock
async def test_cache_hit_historical(client, db_session):
    db_session.add(
        MarsPhoto(
            id=10,
            sol=500,
            earth_date="2019-06-01",
            rover_name="curiosity",
            camera_name="FHAZ",
            img_src="https://mars.example/10.jpg",
            fetched_at=datetime(2019, 6, 1, 12, 0, 0),
        )
    )
    await db_session.commit()

    route = respx.get(f"{_NASA_PHOTOS_BASE}/curiosity/photos")

    response = await client.get(
        "/api/v1/mars/photos",
        params={"rover": "curiosity", "sol": 500, "camera": "FHAZ"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["cached"] is True
    assert body["stale"] is False
    assert not route.called


# ── camera filter ─────────────────────────────────────────────────────────────


@respx.mock
async def test_camera_filter(client, db_session):
    # Two photos: FHAZ and NAVCAM — request only FHAZ
    db_session.add(
        MarsPhoto(
            id=20,
            sol=600,
            earth_date="2019-07-01",
            rover_name="curiosity",
            camera_name="FHAZ",
            img_src="https://mars.example/20.jpg",
            fetched_at=datetime(2019, 7, 1, 0, 0, 0),
        )
    )
    db_session.add(
        MarsPhoto(
            id=21,
            sol=600,
            earth_date="2019-07-01",
            rover_name="curiosity",
            camera_name="NAVCAM",
            img_src="https://mars.example/21.jpg",
            fetched_at=datetime(2019, 7, 1, 0, 0, 0),
        )
    )
    await db_session.commit()

    route = respx.get(f"{_NASA_PHOTOS_BASE}/curiosity/photos")

    response = await client.get(
        "/api/v1/mars/photos",
        params={"rover": "curiosity", "sol": 600, "camera": "FHAZ"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["cached"] is True
    assert len(body["data"]) == 1
    assert body["data"][0]["id"] == 20
    assert not route.called


# ── pagination ────────────────────────────────────────────────────────────────


@respx.mock
async def test_pagination(client, db_session):
    # Seed 25 photos for page 1 and 5 for page 2
    for i in range(30):
        db_session.add(
            MarsPhoto(
                id=100 + i,
                sol=700,
                earth_date="2019-08-01",
                rover_name="curiosity",
                camera_name="MAST",
                img_src=f"https://mars.example/{100 + i}.jpg",
                fetched_at=datetime(2019, 8, 1, 0, 0, 0),
            )
        )
    await db_session.commit()

    route = respx.get(f"{_NASA_PHOTOS_BASE}/curiosity/photos")

    response = await client.get(
        "/api/v1/mars/photos",
        params={"rover": "curiosity", "sol": 700, "camera": "MAST", "page": 2},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["cached"] is True
    # page 2 has photos 25-29 (ids 125-129)
    assert len(body["data"]) == 5
    assert not route.called


# ── today re-fetch ────────────────────────────────────────────────────────────


@respx.mock
async def test_today_refetches(client, db_session):
    today = datetime.now(timezone.utc).date().isoformat()
    db_session.add(
        MarsPhoto(
            id=50,
            sol=9999,
            earth_date=today,
            rover_name="perseverance",
            camera_name="NAVCAM_LEFT",
            img_src="https://mars.example/50.jpg",
            fetched_at=datetime.utcnow() - timedelta(hours=2),
        )
    )
    await db_session.commit()

    respx.get(f"{_NASA_PHOTOS_BASE}/perseverance/photos").mock(
        return_value=httpx.Response(
            200,
            json=_photos_response(
                _photo(50, rover="perseverance", sol=9999, earth_date=today, camera="NAVCAM_LEFT"),
                _photo(51, rover="perseverance", sol=9999, earth_date=today, camera="NAVCAM_LEFT"),
            ),
        )
    )

    response = await client.get(
        "/api/v1/mars/photos",
        params={"rover": "perseverance", "sol": 9999},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["cached"] is False
    assert body["is_today"] is True


# ── stale fallback ────────────────────────────────────────────────────────────


@respx.mock
async def test_stale_fallback(client, db_session):
    today = datetime.now(timezone.utc).date().isoformat()
    db_session.add(
        MarsPhoto(
            id=60,
            sol=8888,
            earth_date=today,
            rover_name="curiosity",
            camera_name="FHAZ",
            img_src="https://mars.example/60.jpg",
            fetched_at=datetime.utcnow() - timedelta(hours=1),
        )
    )
    await db_session.commit()

    respx.get(f"{_NASA_PHOTOS_BASE}/curiosity/photos").mock(
        return_value=httpx.Response(503)
    )

    response = await client.get(
        "/api/v1/mars/photos",
        params={"rover": "curiosity", "sol": 8888},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["cached"] is True
    assert body["stale"] is True
    assert body["is_today"] is True


# ── all four rovers ───────────────────────────────────────────────────────────


@pytest.mark.parametrize("rover", ["curiosity", "opportunity", "spirit", "perseverance"])
@respx.mock
async def test_all_rovers(rover, client):
    respx.get(f"{_NASA_PHOTOS_BASE}/{rover}/photos").mock(
        return_value=httpx.Response(200, json=_photos_response(_photo(999, rover=rover, sol=1)))
    )
    response = await client.get(
        "/api/v1/mars/photos",
        params={"rover": rover, "sol": 1},
    )
    assert response.status_code == 200
    assert response.json()["data"][0]["rover_name"] == rover


# ── error cases ───────────────────────────────────────────────────────────────


@respx.mock
async def test_error_no_cache(client):
    respx.get(f"{_NASA_PHOTOS_BASE}/curiosity/photos").mock(
        return_value=httpx.Response(503)
    )
    response = await client.get(
        "/api/v1/mars/photos",
        params={"rover": "curiosity", "sol": 1234},
    )
    assert response.status_code == 502
    assert response.json()["error"]["code"] == "NASA_UNAVAILABLE"


@respx.mock
async def test_upstream_404_is_reported_as_unavailable(client):
    # The mars-photos backend returning 404 (e.g. its Heroku app being gone)
    # is not a legitimate "not found" — the rover is validated before this
    # call, so any 404 here means the endpoint itself is broken.
    respx.get(f"{_NASA_PHOTOS_BASE}/curiosity/photos").mock(
        return_value=httpx.Response(404)
    )
    response = await client.get(
        "/api/v1/mars/photos",
        params={"rover": "curiosity", "sol": 1237},
    )
    assert response.status_code == 502
    assert response.json()["error"]["code"] == "NASA_UNAVAILABLE"


@respx.mock
async def test_auth_error(client):
    respx.get(f"{_NASA_PHOTOS_BASE}/curiosity/photos").mock(
        return_value=httpx.Response(403)
    )
    response = await client.get(
        "/api/v1/mars/photos",
        params={"rover": "curiosity", "sol": 1235},
    )
    assert response.status_code == 502
    assert response.json()["error"]["code"] == "NASA_AUTH_ERROR"


@respx.mock
async def test_nasa_error_400(client):
    respx.get(f"{_NASA_PHOTOS_BASE}/curiosity/photos").mock(
        return_value=httpx.Response(400)
    )
    response = await client.get(
        "/api/v1/mars/photos",
        params={"rover": "curiosity", "sol": 1236},
    )
    assert response.status_code == 502
    assert response.json()["error"]["code"] == "NASA_ERROR"


@respx.mock
async def test_no_internet(client):
    respx.get(f"{_NASA_PHOTOS_BASE}/curiosity/photos").mock(
        side_effect=httpx.ConnectError("nope")
    )
    respx.head("https://www.google.com").mock(side_effect=httpx.ConnectError("nope"))

    response = await client.get(
        "/api/v1/mars/photos",
        params={"rover": "curiosity", "sol": 1237},
    )
    assert response.status_code == 502
    assert response.json()["error"]["code"] == "NO_INTERNET"


async def test_invalid_rover(client):
    response = await client.get(
        "/api/v1/mars/photos",
        params={"rover": "marvin", "sol": 1},
    )
    assert response.status_code == 400
    assert response.json()["detail"]["error"]["code"] == "INVALID_PARAMS"


async def test_missing_sol_and_earth_date(client):
    response = await client.get(
        "/api/v1/mars/photos",
        params={"rover": "curiosity"},
    )
    assert response.status_code == 400
    assert response.json()["detail"]["error"]["code"] == "INVALID_PARAMS"


# ── empty photos list from NASA ───────────────────────────────────────────────


@respx.mock
async def test_empty_photos_list(client):
    respx.get(f"{_NASA_PHOTOS_BASE}/curiosity/photos").mock(
        return_value=httpx.Response(200, json={"photos": []})
    )
    response = await client.get(
        "/api/v1/mars/photos",
        params={"rover": "curiosity", "sol": 9990},
    )
    assert response.status_code == 200
    assert response.json()["data"] == []
    assert response.json()["cached"] is False


# ── earth_date = today → is_today=True ───────────────────────────────────────


@respx.mock
async def test_earth_date_today_flag(client):
    today = datetime.now(timezone.utc).date().isoformat()
    respx.get(f"{_NASA_PHOTOS_BASE}/curiosity/photos").mock(
        return_value=httpx.Response(
            200,
            json=_photos_response(_photo(70, earth_date=today)),
        )
    )
    response = await client.get(
        "/api/v1/mars/photos",
        params={"rover": "curiosity", "earth_date": today},
    )
    body = response.json()
    assert body["is_today"] is True
    assert body["cached"] is False
