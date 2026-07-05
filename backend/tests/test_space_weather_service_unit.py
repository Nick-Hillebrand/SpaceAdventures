"""Direct unit tests of space_weather_service for coverage of async internals."""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone

import httpx
import pytest
import respx

from app.config import Settings
from app.models import SpaceWeatherEvent
from app.services import space_weather_service
from app.services.nasa_client import NasaClient, NasaClientError


def _client() -> NasaClient:
    settings = Settings(  # type: ignore[call-arg]
        require_secrets=False,
        nasa_api_key="TEST",
        nasa_base_url="https://api.nasa.example",
    )
    return NasaClient(settings)


@pytest.fixture
async def nasa():
    c = _client()
    try:
        yield c
    finally:
        await c.close()


# ── _extract_id ───────────────────────────────────────────────────────────────


def test_extract_id_flr():
    assert space_weather_service._extract_id({"flrID": "FLR-001"}, "FLR") == "FLR-001"


def test_extract_id_gst():
    assert space_weather_service._extract_id({"gstID": "GST-001"}, "GST") == "GST-001"


def test_extract_id_cme_via_activity_id():
    assert space_weather_service._extract_id({"activityID": "CME-001"}, "CME") == "CME-001"


def test_extract_id_sep():
    assert space_weather_service._extract_id({"sepID": "SEP-001"}, "SEP") == "SEP-001"


def test_extract_id_rbe():
    assert space_weather_service._extract_id({"rbeID": "RBE-001"}, "RBE") == "RBE-001"


def test_extract_id_returns_none_when_missing():
    assert space_weather_service._extract_id({}, "FLR") is None


# ── _extract_start_date ────────────────────────────────────────────────────────


def test_extract_start_date_uses_begin_time_for_flr():
    obj = {"beginTime": "2020-06-15T06:00Z"}
    result = space_weather_service._extract_start_date(obj, "FLR", "2020-06-01")
    assert result == "2020-06-15"


def test_extract_start_date_falls_back_to_feed_date():
    result = space_weather_service._extract_start_date({}, "FLR", "2020-06-01")
    assert result == "2020-06-01"


def test_extract_start_date_gst_uses_start_time():
    obj = {"startTime": "2020-07-01T00:00Z"}
    result = space_weather_service._extract_start_date(obj, "GST", "2020-07-00")
    assert result == "2020-07-01"


def test_extract_start_date_rbe_uses_event_time():
    obj = {"eventTime": "2020-08-20T10:00Z"}
    result = space_weather_service._extract_start_date(obj, "RBE", "fallback")
    assert result == "2020-08-20"


# ── _row_from_event ────────────────────────────────────────────────────────────


def test_row_from_event_returns_none_when_no_id():
    row = space_weather_service._row_from_event({}, "FLR", "2020-01-01")
    assert row is None


def test_row_from_event_constructs_correct_id():
    obj = {"flrID": "FLR-XYZ"}
    row = space_weather_service._row_from_event(obj, "FLR", "2020-01-01")
    assert row is not None
    assert row.id == "FLR:FLR-XYZ"
    assert row.event_type == "FLR"


# ── _latest_fetched_at ────────────────────────────────────────────────────────


def test_latest_fetched_at_empty_returns_now():
    before = datetime.now(timezone.utc).replace(tzinfo=None)
    result = space_weather_service._latest_fetched_at([])
    after = datetime.now(timezone.utc).replace(tzinfo=None)
    assert before <= result <= after


# ── _validate_range ────────────────────────────────────────────────────────────


def test_validate_range_reversed_raises():
    with pytest.raises(ValueError):
        space_weather_service._validate_range("2020-02-10", "2020-02-01")


def test_validate_range_same_day_ok():
    s, e = space_weather_service._validate_range("2020-02-05", "2020-02-05")
    assert s == e == date(2020, 2, 5)


# ── fetch_events direct ───────────────────────────────────────────────────────


@respx.mock
async def test_fetch_events_cache_miss_writes_rows(db_session, nasa):
    respx.get("https://api.nasa.example/DONKI/FLR").mock(
        return_value=httpx.Response(
            200,
            json=[{"flrID": "FLR-2020-04-01-1", "beginTime": "2020-04-01T08:00Z", "classType": "C1.0"}],
        )
    )
    result = await space_weather_service.fetch_events(db_session, nasa, "FLR", "2020-04-01", "2020-04-02")
    assert result.cached is False
    assert result.stale is False
    assert len(result.rows) == 1
    assert result.rows[0].event_type == "FLR"


@respx.mock
async def test_fetch_events_cache_hit(db_session, nasa):
    db_session.add(
        SpaceWeatherEvent(
            id="GST:GST-2020-05-01",
            event_type="GST",
            start_date="2020-05-01",
            raw_json=json.dumps({"gstID": "GST-2020-05-01"}),
            fetched_at=datetime(2020, 5, 1, 12, 0, 0),
        )
    )
    await db_session.commit()

    with respx.mock:
        route = respx.get("https://api.nasa.example/DONKI/GST")
        result = await space_weather_service.fetch_events(db_session, nasa, "GST", "2020-05-01", "2020-05-02")

    assert result.cached is True
    assert route.called is False


@respx.mock
async def test_fetch_events_stale_fallback(db_session, nasa):
    today = datetime.now(timezone.utc).date().isoformat()
    db_session.add(
        SpaceWeatherEvent(
            id="CME:CME-today-1",
            event_type="CME",
            start_date=today,
            raw_json=json.dumps({"activityID": "CME-today-1"}),
            fetched_at=datetime.utcnow() - timedelta(hours=2),
        )
    )
    await db_session.commit()

    respx.get("https://api.nasa.example/DONKI/CME").mock(return_value=httpx.Response(503))
    result = await space_weather_service.fetch_events(db_session, nasa, "CME", today, today)
    assert result.stale is True
    assert result.is_today is True


@respx.mock
async def test_fetch_events_upstream_error_no_cache_raises(db_session, nasa):
    respx.get("https://api.nasa.example/DONKI/SEP").mock(return_value=httpx.Response(503))
    with pytest.raises(NasaClientError):
        await space_weather_service.fetch_events(db_session, nasa, "SEP", "2020-06-01", "2020-06-02")


@respx.mock
async def test_fetch_events_upsert_updates_existing(db_session, nasa):
    today = datetime.now(timezone.utc).date().isoformat()
    db_session.add(
        SpaceWeatherEvent(
            id="RBE:RBE-today-1",
            event_type="RBE",
            start_date=today,
            raw_json=json.dumps({"rbeID": "RBE-today-1", "old": True}),
            fetched_at=datetime.utcnow() - timedelta(hours=6),
        )
    )
    await db_session.commit()

    respx.get("https://api.nasa.example/DONKI/RBE").mock(
        return_value=httpx.Response(200, json=[{"rbeID": "RBE-today-1", "updated": True}])
    )
    result = await space_weather_service.fetch_events(db_session, nasa, "RBE", today, today)
    assert result.cached is False

    row = await db_session.get(SpaceWeatherEvent, "RBE:RBE-today-1")
    stored = json.loads(row.raw_json)
    assert stored.get("updated") is True


@respx.mock
async def test_fetch_events_null_response_treated_as_empty(db_session, nasa):
    respx.get("https://api.nasa.example/DONKI/FLR").mock(
        return_value=httpx.Response(200, text="null", headers={"content-type": "application/json"})
    )
    result = await space_weather_service.fetch_events(db_session, nasa, "FLR", "2020-07-01", "2020-07-02")
    assert result.cached is False
    assert result.rows == []


def test_space_weather_result_fields():
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    r = space_weather_service.SpaceWeatherResult(
        rows=[], cached=False, stale=True, is_today=True, fetched_at=now
    )
    assert r.stale is True
    assert r.rows == []
