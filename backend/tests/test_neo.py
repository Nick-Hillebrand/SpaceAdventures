from __future__ import annotations

from datetime import datetime, timedelta, timezone

import httpx
import respx
from sqlalchemy import select

from app.models import Neo


def _feed_payload(dates: list[str]) -> dict:
    near: dict[str, list[dict]] = {}
    for i, d in enumerate(dates):
        near[d] = [
            {
                "id": f"{d}-1",
                "name": f"NEO {d} A",
                "absolute_magnitude_h": 22.5 + i,
                "estimated_diameter": {
                    "kilometers": {
                        "estimated_diameter_min": 0.1 + i * 0.01,
                        "estimated_diameter_max": 0.3 + i * 0.01,
                    }
                },
                "is_potentially_hazardous_asteroid": bool(i % 2),
                "close_approach_data": [
                    {
                        "close_approach_date": d,
                        "relative_velocity": {"kilometers_per_hour": f"{10000 + i * 100}"},
                        "miss_distance": {"kilometers": f"{500000 + i * 1000}"},
                        "orbiting_body": "Earth",
                    }
                ],
                "nasa_jpl_url": f"https://jpl.example/{d}",
            }
        ]
    return {"element_count": len(dates), "near_earth_objects": near}


@respx.mock
async def test_get_neo_feed_live_cache_miss(client, db_session):
    respx.get("https://api.nasa.example/neo/rest/v1/feed").mock(
        return_value=httpx.Response(200, json=_feed_payload(["2020-01-01", "2020-01-02"])),
    )

    response = await client.get(
        "/api/v1/neo/feed",
        params={"start": "2020-01-01", "end": "2020-01-02"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["cached"] is False
    assert body["stale"] is False
    assert body["is_today"] is False
    assert len(body["data"]) == 2
    ids = {row["id"] for row in body["data"]}
    assert ids == {"2020-01-01-1", "2020-01-02-1"}

    rows = (await db_session.execute(select(Neo))).scalars().all()
    assert len(rows) == 2


@respx.mock
async def test_get_neo_feed_cache_hit_historical(client, db_session):
    db_session.add(
        Neo(
            id="cached-1",
            name="Old NEO",
            close_approach_date="2020-01-10",
            is_potentially_hazardous=False,
            fetched_at=datetime(2020, 1, 10, 12, 0, 0),
        )
    )
    await db_session.commit()

    route = respx.get("https://api.nasa.example/neo/rest/v1/feed")

    response = await client.get(
        "/api/v1/neo/feed",
        params={"start": "2020-01-10", "end": "2020-01-11"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["cached"] is True
    assert body["stale"] is False
    assert body["is_today"] is False
    assert len(body["data"]) == 1
    assert body["data"][0]["id"] == "cached-1"
    assert not route.called


@respx.mock
async def test_get_neo_feed_today_refetches(client, db_session):
    today = datetime.now(timezone.utc).date().isoformat()
    db_session.add(
        Neo(
            id="today-old",
            name="Morning cache",
            close_approach_date=today,
            is_potentially_hazardous=False,
            fetched_at=datetime.utcnow() - timedelta(hours=2),
        )
    )
    await db_session.commit()

    fresh = _feed_payload([today])
    fresh["near_earth_objects"][today][0]["id"] = "today-fresh"
    fresh["near_earth_objects"][today][0]["name"] = "Fresh NEO"
    respx.get("https://api.nasa.example/neo/rest/v1/feed").mock(
        return_value=httpx.Response(200, json=fresh),
    )

    response = await client.get(
        "/api/v1/neo/feed",
        params={"start": today, "end": today},
    )
    body = response.json()
    assert response.status_code == 200
    assert body["cached"] is False
    assert body["is_today"] is True
    ids = {row["id"] for row in body["data"]}
    assert "today-fresh" in ids


@respx.mock
async def test_get_neo_feed_stale_fallback(client, db_session):
    today = datetime.now(timezone.utc).date().isoformat()
    db_session.add(
        Neo(
            id="today-cached",
            name="Cached today",
            close_approach_date=today,
            is_potentially_hazardous=False,
            fetched_at=datetime.utcnow() - timedelta(hours=1),
        )
    )
    await db_session.commit()

    respx.get("https://api.nasa.example/neo/rest/v1/feed").mock(
        return_value=httpx.Response(503),
    )

    response = await client.get(
        "/api/v1/neo/feed",
        params={"start": today, "end": today},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["cached"] is True
    assert body["stale"] is True
    assert body["is_today"] is True
    assert body["data"][0]["id"] == "today-cached"


@respx.mock
async def test_get_neo_feed_error_no_cache(client):
    respx.get("https://api.nasa.example/neo/rest/v1/feed").mock(
        return_value=httpx.Response(503),
    )
    response = await client.get(
        "/api/v1/neo/feed",
        params={"start": "2020-02-01", "end": "2020-02-02"},
    )
    assert response.status_code == 502
    assert response.json()["error"]["code"] == "NASA_UNAVAILABLE"


@respx.mock
async def test_get_neo_feed_auth_error(client):
    respx.get("https://api.nasa.example/neo/rest/v1/feed").mock(
        return_value=httpx.Response(403),
    )
    response = await client.get(
        "/api/v1/neo/feed",
        params={"start": "2020-02-03", "end": "2020-02-04"},
    )
    assert response.status_code == 502
    assert response.json()["error"]["code"] == "NASA_AUTH_ERROR"


@respx.mock
async def test_get_neo_feed_nasa_error(client):
    respx.get("https://api.nasa.example/neo/rest/v1/feed").mock(
        return_value=httpx.Response(400, json={"error_message": "bad params"}),
    )
    response = await client.get(
        "/api/v1/neo/feed",
        params={"start": "2020-02-05", "end": "2020-02-06"},
    )
    assert response.status_code == 502
    assert response.json()["error"]["code"] == "NASA_ERROR"


@respx.mock
async def test_get_neo_feed_no_internet(client):
    respx.get("https://api.nasa.example/neo/rest/v1/feed").mock(
        side_effect=httpx.ConnectError("nope"),
    )
    respx.head("https://www.google.com").mock(side_effect=httpx.ConnectError("nope"))

    response = await client.get(
        "/api/v1/neo/feed",
        params={"start": "2020-02-07", "end": "2020-02-08"},
    )
    assert response.status_code == 502
    assert response.json()["error"]["code"] == "NO_INTERNET"


async def test_get_neo_feed_invalid_date(client):
    response = await client.get(
        "/api/v1/neo/feed",
        params={"start": "not-a-date", "end": "2020-02-08"},
    )
    assert response.status_code == 400
    assert response.json()["detail"]["error"]["code"] == "INVALID_RANGE"


async def test_get_neo_feed_reversed_range(client):
    response = await client.get(
        "/api/v1/neo/feed",
        params={"start": "2020-02-10", "end": "2020-02-01"},
    )
    assert response.status_code == 400
    assert response.json()["detail"]["error"]["code"] == "INVALID_RANGE"


async def test_get_neo_feed_range_too_long(client):
    response = await client.get(
        "/api/v1/neo/feed",
        params={"start": "2020-02-01", "end": "2020-02-15"},
    )
    assert response.status_code == 400
    assert response.json()["detail"]["error"]["code"] == "INVALID_RANGE"


@respx.mock
async def test_get_neo_feed_upsert_updates_existing_row(client, db_session):
    db_session.add(
        Neo(
            id="2020-03-01-1",
            name="Stale name",
            close_approach_date="2020-03-01",
            is_potentially_hazardous=False,
            fetched_at=datetime(2020, 3, 1, 6, 0, 0),
        )
    )
    await db_session.commit()

    # Historical + cache present → cache hit only. We need to force a fetch
    # by clearing the cache first, so instead we make the request include
    # today so the upsert branch is exercised.
    today = datetime.now(timezone.utc).date().isoformat()
    payload = _feed_payload([today])
    payload["near_earth_objects"][today][0]["id"] = "2020-03-01-1"
    payload["near_earth_objects"][today][0]["name"] = "Renamed"
    respx.get("https://api.nasa.example/neo/rest/v1/feed").mock(
        return_value=httpx.Response(200, json=payload),
    )

    response = await client.get(
        "/api/v1/neo/feed",
        params={"start": today, "end": today},
    )
    assert response.status_code == 200
    row = await db_session.get(Neo, "2020-03-01-1")
    assert row is not None
    assert row.name == "Renamed"


@respx.mock
async def test_get_neo_feed_handles_missing_optional_fields(client):
    today = datetime.now(timezone.utc).date().isoformat()
    payload = {
        "element_count": 1,
        "near_earth_objects": {
            today: [
                {
                    "id": "minimal",
                    "name": "Minimal",
                    # No absolute_magnitude_h, no estimated_diameter,
                    # no close_approach_data, no nasa_jpl_url
                }
            ]
        },
    }
    respx.get("https://api.nasa.example/neo/rest/v1/feed").mock(
        return_value=httpx.Response(200, json=payload),
    )
    response = await client.get(
        "/api/v1/neo/feed",
        params={"start": today, "end": today},
    )
    assert response.status_code == 200
    body = response.json()
    assert len(body["data"]) == 1
    row = body["data"][0]
    assert row["id"] == "minimal"
    assert row["absolute_magnitude_h"] is None
    assert row["estimated_diameter_min_km"] is None
    assert row["relative_velocity_kph"] is None
    assert row["miss_distance_km"] is None
    assert row["is_potentially_hazardous"] is False
    assert row["close_approach_date"] == today


@respx.mock
async def test_get_neo_feed_coerces_non_numeric_gracefully(client):
    today = datetime.now(timezone.utc).date().isoformat()
    payload = {
        "element_count": 1,
        "near_earth_objects": {
            today: [
                {
                    "id": "junk",
                    "name": "Junk",
                    "absolute_magnitude_h": "not-a-number",
                    "estimated_diameter": {
                        "kilometers": {
                            "estimated_diameter_min": "oops",
                            "estimated_diameter_max": None,
                        }
                    },
                    "is_potentially_hazardous_asteroid": False,
                    "close_approach_data": [
                        {
                            "close_approach_date": today,
                            "relative_velocity": {"kilometers_per_hour": "bad"},
                            "miss_distance": {"kilometers": None},
                            "orbiting_body": "Earth",
                        }
                    ],
                }
            ]
        },
    }
    respx.get("https://api.nasa.example/neo/rest/v1/feed").mock(
        return_value=httpx.Response(200, json=payload),
    )
    response = await client.get(
        "/api/v1/neo/feed",
        params={"start": today, "end": today},
    )
    assert response.status_code == 200
    row = response.json()["data"][0]
    assert row["absolute_magnitude_h"] is None
    assert row["estimated_diameter_min_km"] is None
    assert row["relative_velocity_kph"] is None
    assert row["miss_distance_km"] is None
