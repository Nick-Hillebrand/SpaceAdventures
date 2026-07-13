from __future__ import annotations

from datetime import datetime, timedelta, timezone

import httpx
import pytest
import respx
from sqlalchemy import select

from app.models import SpaceWeatherEvent

# ── helpers ──────────────────────────────────────────────────────────────────

_ROUTES = {
    "FLR": "/api/v1/space-weather/flares",
    "GST": "/api/v1/space-weather/storms",
    "CME": "/api/v1/space-weather/cmes",
    "SEP": "/api/v1/space-weather/sep",
    "RBE": "/api/v1/space-weather/rbe",
}

_DONKI_URL_BASE = "https://api.nasa.example/DONKI"

_DONKI_PATHS = {
    "FLR": f"{_DONKI_URL_BASE}/FLR",
    "GST": f"{_DONKI_URL_BASE}/GST",
    "CME": f"{_DONKI_URL_BASE}/CME",
    "SEP": f"{_DONKI_URL_BASE}/SEP",
    "RBE": f"{_DONKI_URL_BASE}/RBE",
}


def _flr_event(date: str, n: int = 1) -> dict:
    return {
        "flrID": f"FLR-{date}-{n}",
        "beginTime": f"{date}T06:00Z",
        "peakTime": f"{date}T06:30Z",
        "classType": "M1.0",
        "activeRegionNum": 12345,
    }


def _gst_event(date: str, n: int = 1) -> dict:
    return {
        "gstID": f"GST-{date}-{n}",
        "startTime": f"{date}T00:00Z",
        "allKpIndex": [{"observedTime": f"{date}T03:00Z", "kpIndex": 5}],
    }


def _cme_event(date: str, n: int = 1) -> dict:
    return {
        "activityID": f"CME-{date}-{n}",
        "startTime": f"{date}T12:00Z",
        "catalog": "M2M_CATALOG",
        "note": "test CME",
    }


def _sep_event(date: str, n: int = 1) -> dict:
    return {
        "sepID": f"SEP-{date}-{n}",
        "eventTime": f"{date}T08:00Z",
        "instruments": [{"displayName": "GOES-16: EPEAD 10MeV"}],
    }


def _rbe_event(date: str, n: int = 1) -> dict:
    return {
        "rbeID": f"RBE-{date}-{n}",
        "eventTime": f"{date}T10:00Z",
        "rbID": "2020-01-01-RBE-01",
    }


_SAMPLE_EVENTS = {
    "FLR": _flr_event,
    "GST": _gst_event,
    "CME": _cme_event,
    "SEP": _sep_event,
    "RBE": _rbe_event,
}


def _seed_event(event_type: str, date: str, n: int = 1) -> SpaceWeatherEvent:
    builder = _SAMPLE_EVENTS[event_type]
    raw = builder(date, n)
    id_val = raw.get(f"{event_type.lower()}ID") or raw.get("activityID") or raw.get("gstID")
    return SpaceWeatherEvent(
        id=f"{event_type}:{id_val}",
        event_type=event_type,
        start_date=date,
        raw_json=raw,
        fetched_at=datetime(2020, 1, 1, 12, 0, 0),
    )


# ── per-event-type live fetch (cache miss) ────────────────────────────────────


@pytest.mark.parametrize(
    "event_type,route",
    [
        ("FLR", "/api/v1/space-weather/flares"),
        ("GST", "/api/v1/space-weather/storms"),
        ("CME", "/api/v1/space-weather/cmes"),
        ("SEP", "/api/v1/space-weather/sep"),
        ("RBE", "/api/v1/space-weather/rbe"),
    ],
)
@respx.mock
async def test_cache_miss_all_event_types(event_type, route, client, db_session):
    builder = _SAMPLE_EVENTS[event_type]
    payload = [builder("2020-01-05")]
    respx.get(_DONKI_PATHS[event_type]).mock(return_value=httpx.Response(200, json=payload))

    response = await client.get(route, params={"start": "2020-01-05", "end": "2020-01-06"})
    assert response.status_code == 200
    body = response.json()
    assert body["cached"] is False
    assert body["stale"] is False
    assert body["is_today"] is False
    assert len(body["data"]) == 1
    assert body["data"][0]["event_type"] == event_type

    rows = (await db_session.execute(select(SpaceWeatherEvent))).scalars().all()
    assert len(rows) == 1


# ── cache hit (historical) ────────────────────────────────────────────────────


@respx.mock
async def test_cache_hit_historical(client, db_session):
    db_session.add(_seed_event("FLR", "2020-02-01"))
    await db_session.commit()

    route = respx.get(_DONKI_PATHS["FLR"])

    response = await client.get(
        "/api/v1/space-weather/flares",
        params={"start": "2020-02-01", "end": "2020-02-02"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["cached"] is True
    assert body["stale"] is False
    assert not route.called
    assert len(body["data"]) == 1


# ── today re-fetch ────────────────────────────────────────────────────────────


@respx.mock
async def test_today_refetches(client, db_session):
    today = datetime.now(timezone.utc).date().isoformat()
    db_session.add(_seed_event("GST", today))
    await db_session.commit()

    fresh_event = _gst_event(today, n=99)
    fresh_event["gstID"] = f"GST-{today}-99"
    respx.get(_DONKI_PATHS["GST"]).mock(
        return_value=httpx.Response(200, json=[fresh_event])
    )

    response = await client.get(
        "/api/v1/space-weather/storms",
        params={"start": today, "end": today},
    )
    body = response.json()
    assert response.status_code == 200
    assert body["cached"] is False
    assert body["is_today"] is True
    ids = [row["id"] for row in body["data"]]
    assert any("99" in i for i in ids)


# ── stale fallback ────────────────────────────────────────────────────────────


@respx.mock
async def test_stale_fallback(client, db_session):
    today = datetime.now(timezone.utc).date().isoformat()
    db_session.add(_seed_event("CME", today))
    await db_session.commit()

    respx.get(_DONKI_PATHS["CME"]).mock(return_value=httpx.Response(503))

    response = await client.get(
        "/api/v1/space-weather/cmes",
        params={"start": today, "end": today},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["cached"] is True
    assert body["stale"] is True
    assert body["is_today"] is True


# ── error with no cache ───────────────────────────────────────────────────────


@respx.mock
async def test_error_no_cache(client):
    respx.get(_DONKI_PATHS["SEP"]).mock(return_value=httpx.Response(503))

    response = await client.get(
        "/api/v1/space-weather/sep",
        params={"start": "2020-03-01", "end": "2020-03-02"},
    )
    assert response.status_code == 502
    assert response.json()["error"]["code"] == "NASA_UNAVAILABLE"


@respx.mock
async def test_auth_error(client):
    respx.get(_DONKI_PATHS["RBE"]).mock(return_value=httpx.Response(403))

    response = await client.get(
        "/api/v1/space-weather/rbe",
        params={"start": "2020-03-03", "end": "2020-03-04"},
    )
    assert response.status_code == 502
    assert response.json()["error"]["code"] == "NASA_AUTH_ERROR"


@respx.mock
async def test_nasa_error(client):
    respx.get(_DONKI_PATHS["FLR"]).mock(return_value=httpx.Response(400))

    response = await client.get(
        "/api/v1/space-weather/flares",
        params={"start": "2020-03-05", "end": "2020-03-06"},
    )
    assert response.status_code == 502
    assert response.json()["error"]["code"] == "NASA_ERROR"


@respx.mock
async def test_no_internet(client):
    respx.get(_DONKI_PATHS["GST"]).mock(side_effect=httpx.ConnectError("nope"))
    respx.head("https://www.google.com").mock(side_effect=httpx.ConnectError("nope"))

    response = await client.get(
        "/api/v1/space-weather/storms",
        params={"start": "2020-03-07", "end": "2020-03-08"},
    )
    assert response.status_code == 502
    assert response.json()["error"]["code"] == "NO_INTERNET"


# ── validation errors ─────────────────────────────────────────────────────────


async def test_invalid_date(client):
    response = await client.get(
        "/api/v1/space-weather/flares",
        params={"start": "bad", "end": "2020-01-05"},
    )
    assert response.status_code == 400
    assert response.json()["detail"]["error"]["code"] == "INVALID_RANGE"


async def test_reversed_range(client):
    response = await client.get(
        "/api/v1/space-weather/cmes",
        params={"start": "2020-05-10", "end": "2020-05-01"},
    )
    assert response.status_code == 400
    assert response.json()["detail"]["error"]["code"] == "INVALID_RANGE"


# ── DONKI returns null (no events) ────────────────────────────────────────────


@respx.mock
async def test_empty_response_from_donki(client):
    # DONKI returns the JSON literal null when no events — treated as empty list
    respx.get(_DONKI_PATHS["SEP"]).mock(
        return_value=httpx.Response(200, text="null", headers={"content-type": "application/json"})
    )

    response = await client.get(
        "/api/v1/space-weather/sep",
        params={"start": "2020-04-01", "end": "2020-04-02"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["data"] == []
    assert body["cached"] is False


# ── upsert updates an existing row ───────────────────────────────────────────


@respx.mock
async def test_upsert_updates_existing_row(client, db_session):
    today = datetime.now(timezone.utc).date().isoformat()

    orig_raw = _flr_event(today)
    db_session.add(
        SpaceWeatherEvent(
            id=f"FLR:FLR-{today}-1",
            event_type="FLR",
            start_date=today,
            raw_json=orig_raw,
            fetched_at=datetime.utcnow() - timedelta(hours=4),
        )
    )
    await db_session.commit()

    updated = _flr_event(today)
    updated["classType"] = "X1.0"  # changed
    respx.get(_DONKI_PATHS["FLR"]).mock(return_value=httpx.Response(200, json=[updated]))

    response = await client.get(
        "/api/v1/space-weather/flares",
        params={"start": today, "end": today},
    )
    assert response.status_code == 200
    assert response.json()["cached"] is False

    row = await db_session.get(SpaceWeatherEvent, f"FLR:FLR-{today}-1")
    assert row is not None
    assert row.raw_json["classType"] == "X1.0"


# ── events with no ID field are skipped ──────────────────────────────────────


@respx.mock
async def test_event_without_id_skipped(client):
    # Event missing all known ID fields
    payload = [{"beginTime": "2020-05-01T00:00Z", "classType": "B1.0"}]
    respx.get(_DONKI_PATHS["FLR"]).mock(return_value=httpx.Response(200, json=payload))

    response = await client.get(
        "/api/v1/space-weather/flares",
        params={"start": "2020-05-01", "end": "2020-05-02"},
    )
    assert response.status_code == 200
    assert response.json()["data"] == []
