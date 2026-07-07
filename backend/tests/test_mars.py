from __future__ import annotations

from datetime import datetime, timedelta, timezone

import httpx
import pytest
import respx
from sqlalchemy import select

from app.models import MarsPhoto

MSL_BASE = "https://mars.nasa.gov/api/v1/raw_image_items/"
M20_BASE = "https://mars.nasa.gov/rss/api/"


def _msl_item(
    item_id: int,
    sol: int = 1000,
    date_taken: str = "2020-01-01T00:00:00Z",
    instrument: str = "FHAZ_LEFT_A",
) -> dict:
    return {
        "id": item_id,
        "sol": sol,
        "date_taken": date_taken,
        "instrument": instrument,
        "https_url": f"https://mars.nasa.gov/{item_id}.jpg",
    }


def _msl_payload(*items: dict, more: bool = False) -> dict:
    return {"items": list(items), "more": more, "total": len(items)}


def _m20_image(
    image_id: str,
    sol: int = 9999,
    date_taken: str = "2021-03-01T00:00:00Z",
    instrument: str = "NAVCAM_LEFT",
) -> dict:
    return {
        "imageid": image_id,
        "sol": sol,
        "date_taken_utc": date_taken,
        "camera": {"instrument": instrument},
        "image_files": {"full_res": f"https://mars.nasa.gov/{image_id}.jpg"},
    }


def _m20_payload(*images: dict) -> dict:
    return {"images": list(images), "num_images": len(images)}


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
    perseverance = next(r for r in body["data"] if r["name"] == "perseverance")
    assert "SUPERCAM_RMI" in perseverance["cameras"]


# ── cache miss (sol) ──────────────────────────────────────────────────────────


@respx.mock
async def test_get_photos_by_sol_cache_miss(client, db_session):
    respx.get(MSL_BASE).mock(
        return_value=httpx.Response(200, json=_msl_payload(_msl_item(1, sol=1000)))
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
    respx.get(MSL_BASE).mock(
        return_value=httpx.Response(
            200, json=_msl_payload(_msl_item(2, date_taken="2020-03-15T00:00:00Z"))
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

    route = respx.get(MSL_BASE)

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

    route = respx.get(MSL_BASE)

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

    route = respx.get(MSL_BASE)

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

    respx.get(M20_BASE).mock(
        return_value=httpx.Response(
            200,
            json=_m20_payload(
                _m20_image("IMG50", sol=9999, date_taken=f"{today}T00:00:00Z"),
                _m20_image("IMG51", sol=9999, date_taken=f"{today}T00:00:00Z"),
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

    respx.get(MSL_BASE).mock(return_value=httpx.Response(503))

    response = await client.get(
        "/api/v1/mars/photos",
        params={"rover": "curiosity", "sol": 8888},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["cached"] is True
    assert body["stale"] is True
    assert body["is_today"] is True


# ── live rovers (curiosity, perseverance) ─────────────────────────────────────


async def test_curiosity_live_fetch(client):
    with respx.mock:
        respx.get(MSL_BASE).mock(
            return_value=httpx.Response(200, json=_msl_payload(_msl_item(900, sol=1)))
        )
        response = await client.get(
            "/api/v1/mars/photos", params={"rover": "curiosity", "sol": 1}
        )
    assert response.status_code == 200
    assert response.json()["data"][0]["rover_name"] == "curiosity"


async def test_perseverance_live_fetch(client):
    with respx.mock:
        respx.get(M20_BASE).mock(
            return_value=httpx.Response(200, json=_m20_payload(_m20_image("IMGP1", sol=1)))
        )
        response = await client.get(
            "/api/v1/mars/photos", params={"rover": "perseverance", "sol": 1}
        )
    assert response.status_code == 200
    assert response.json()["data"][0]["rover_name"] == "perseverance"


# ── no-live-source rovers (opportunity, spirit) ───────────────────────────────


@pytest.mark.parametrize("rover", ["opportunity", "spirit"])
async def test_no_live_source_rovers_without_cache_return_distinct_error(client, rover):
    with respx.mock:
        response = await client.get(
            "/api/v1/mars/photos", params={"rover": rover, "sol": 1}
        )
    assert response.status_code == 502
    assert response.json()["error"]["code"] == "MARS_NO_LIVE_SOURCE"


@pytest.mark.parametrize("rover", ["opportunity", "spirit"])
async def test_no_live_source_rovers_serve_cache_when_present(client, db_session, rover):
    db_session.add(
        MarsPhoto(
            id=999,
            sol=1,
            earth_date="2004-01-01",
            rover_name=rover,
            camera_name="PANCAM",
            img_src="https://mars.example/999.jpg",
            fetched_at=datetime(2004, 1, 1, 0, 0, 0),
        )
    )
    await db_session.commit()

    with respx.mock:
        response = await client.get(
            "/api/v1/mars/photos", params={"rover": rover, "sol": 1}
        )
    assert response.status_code == 200
    body = response.json()
    assert body["cached"] is True
    assert body["stale"] is False
    assert len(body["data"]) == 1


# ── error cases ───────────────────────────────────────────────────────────────


@respx.mock
async def test_error_no_cache(client):
    respx.get(MSL_BASE).mock(return_value=httpx.Response(503))
    response = await client.get(
        "/api/v1/mars/photos",
        params={"rover": "curiosity", "sol": 1234},
    )
    assert response.status_code == 502
    assert response.json()["error"]["code"] == "MARS_ARCHIVE_UNAVAILABLE"


@respx.mock
async def test_upstream_404_is_reported_as_unavailable(client):
    respx.get(MSL_BASE).mock(return_value=httpx.Response(404))
    response = await client.get(
        "/api/v1/mars/photos",
        params={"rover": "curiosity", "sol": 1237},
    )
    assert response.status_code == 502
    assert response.json()["error"]["code"] == "MARS_ARCHIVE_UNAVAILABLE"


@respx.mock
async def test_invalid_json_is_reported_as_unavailable(client):
    respx.get(MSL_BASE).mock(return_value=httpx.Response(200, content=b"not json"))
    response = await client.get(
        "/api/v1/mars/photos",
        params={"rover": "curiosity", "sol": 1238},
    )
    assert response.status_code == 502
    assert response.json()["error"]["code"] == "MARS_ARCHIVE_UNAVAILABLE"


@respx.mock
async def test_connect_error_is_reported_as_unavailable(client):
    respx.get(MSL_BASE).mock(side_effect=httpx.ConnectError("nope"))
    response = await client.get(
        "/api/v1/mars/photos",
        params={"rover": "curiosity", "sol": 1239},
    )
    assert response.status_code == 502
    assert response.json()["error"]["code"] == "MARS_ARCHIVE_UNAVAILABLE"


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


# ── empty photos list from upstream ───────────────────────────────────────────


@respx.mock
async def test_empty_photos_list(client):
    respx.get(MSL_BASE).mock(return_value=httpx.Response(200, json=_msl_payload()))
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
    respx.get(MSL_BASE).mock(
        return_value=httpx.Response(
            200, json=_msl_payload(_msl_item(70, date_taken=f"{today}T00:00:00Z"))
        )
    )
    response = await client.get(
        "/api/v1/mars/photos",
        params={"rover": "curiosity", "earth_date": today},
    )
    body = response.json()
    assert body["is_today"] is True
    assert body["cached"] is False
