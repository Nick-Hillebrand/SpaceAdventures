from __future__ import annotations

from datetime import datetime, timedelta, timezone

import httpx
import pytest
import respx
from sqlalchemy import select

from app.models import Apod


def _apod_payload(date: str) -> dict:
    return {
        "date": date,
        "title": "Great APOD",
        "explanation": "Cool",
        "url": "https://example.com/img.jpg",
        "hdurl": "https://example.com/hd.jpg",
        "media_type": "image",
        "copyright": "NASA",
    }


@respx.mock
async def test_get_apod_live_cache_miss(client, db_session):
    respx.get("https://api.nasa.example/planetary/apod").mock(
        return_value=httpx.Response(200, json=_apod_payload("2020-01-01")),
    )

    response = await client.get("/api/v1/apod", params={"date": "2020-01-01"})
    assert response.status_code == 200
    body = response.json()
    assert body["cached"] is False
    assert body["stale"] is False
    assert body["is_today"] is False
    assert body["data"]["title"] == "Great APOD"

    row = (await db_session.execute(select(Apod))).scalar_one()
    assert row.date == "2020-01-01"


@respx.mock
async def test_get_apod_cache_hit_historical(client, db_session):
    # Prime cache
    db_session.add(
        Apod(
            date="2020-01-02",
            title="Cached title",
            explanation="e",
            url="u",
            media_type="image",
            fetched_at=datetime(2020, 1, 2, 12, 0, 0),
        )
    )
    await db_session.commit()

    route = respx.get("https://api.nasa.example/planetary/apod")

    response = await client.get("/api/v1/apod", params={"date": "2020-01-02"})
    assert response.status_code == 200
    body = response.json()
    assert body["cached"] is True
    assert body["stale"] is False
    assert body["data"]["title"] == "Cached title"
    assert not route.called


@respx.mock
async def test_get_apod_today_refetches(client, db_session):
    today = datetime.now(timezone.utc).date().isoformat()

    db_session.add(
        Apod(
            date=today,
            title="Stale morning cache",
            explanation="e",
            url="u",
            media_type="image",
            fetched_at=datetime.utcnow() - timedelta(hours=2),
        )
    )
    await db_session.commit()

    payload = _apod_payload(today)
    payload["title"] = "Refreshed"
    respx.get("https://api.nasa.example/planetary/apod").mock(
        return_value=httpx.Response(200, json=payload),
    )

    response = await client.get("/api/v1/apod", params={"date": today})
    body = response.json()
    assert body["cached"] is False
    assert body["is_today"] is True
    assert body["data"]["title"] == "Refreshed"


@respx.mock
async def test_get_apod_stale_fallback(client, db_session):
    db_session.add(
        Apod(
            date="2020-05-05",
            title="Prev",
            explanation="e",
            url="u",
            media_type="image",
            fetched_at=datetime(2020, 5, 5, 8, 0, 0),
        )
    )
    await db_session.commit()

    # Simulate NASA returning 503 — should fall back to cache with stale=True
    today = datetime.now(timezone.utc).date().isoformat()
    # But historical dates don't re-fetch. Use today to trigger the re-fetch path.
    db_session.add(
        Apod(
            date=today,
            title="Today prev",
            explanation="e",
            url="u",
            media_type="image",
            fetched_at=datetime.utcnow() - timedelta(hours=1),
        )
    )
    await db_session.commit()

    respx.get("https://api.nasa.example/planetary/apod").mock(
        return_value=httpx.Response(503),
    )

    response = await client.get("/api/v1/apod", params={"date": today})
    body = response.json()
    assert response.status_code == 200
    assert body["cached"] is True
    assert body["stale"] is True
    assert body["is_today"] is True


@respx.mock
async def test_get_apod_error_no_cache(client):
    respx.get("https://api.nasa.example/planetary/apod").mock(
        return_value=httpx.Response(503),
    )

    response = await client.get("/api/v1/apod", params={"date": "2020-06-06"})
    assert response.status_code == 502
    body = response.json()
    assert body["error"]["code"] == "NASA_UNAVAILABLE"


@respx.mock
async def test_get_apod_auth_error(client):
    respx.get("https://api.nasa.example/planetary/apod").mock(
        return_value=httpx.Response(403),
    )
    response = await client.get("/api/v1/apod", params={"date": "2020-06-07"})
    assert response.status_code == 502
    assert response.json()["error"]["code"] == "NASA_AUTH_ERROR"


@respx.mock
async def test_get_apod_no_internet(client):
    respx.get("https://api.nasa.example/planetary/apod").mock(
        side_effect=httpx.ConnectError("nope")
    )
    respx.head("https://www.google.com").mock(side_effect=httpx.ConnectError("nope"))

    response = await client.get("/api/v1/apod", params={"date": "2020-06-08"})
    assert response.status_code == 502
    assert response.json()["error"]["code"] == "NO_INTERNET"


async def test_get_apod_invalid_date(client):
    response = await client.get("/api/v1/apod", params={"date": "not-a-date"})
    assert response.status_code == 400
    assert response.json()["detail"]["error"]["code"] == "INVALID_DATE"


@respx.mock
async def test_get_apod_defaults_to_today(client):
    today = datetime.now(timezone.utc).date().isoformat()
    respx.get("https://api.nasa.example/planetary/apod").mock(
        return_value=httpx.Response(200, json=_apod_payload(today)),
    )
    response = await client.get("/api/v1/apod")
    body = response.json()
    assert body["is_today"] is True
    assert body["cached"] is False
