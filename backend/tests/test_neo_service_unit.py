"""Direct unit tests of neo_service — bypass FastAPI for coverage instrumentation."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import httpx
import pytest
import respx

from app.config import Settings
from app.models import Neo
from app.services import neo_service
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


def _payload(target_date: str, hazardous: bool = False, name: str = "NEO A") -> dict:
    return {
        "element_count": 1,
        "near_earth_objects": {
            target_date: [
                {
                    "id": f"{target_date}-A",
                    "name": name,
                    "absolute_magnitude_h": 22.1,
                    "estimated_diameter": {
                        "kilometers": {
                            "estimated_diameter_min": 0.10,
                            "estimated_diameter_max": 0.25,
                        }
                    },
                    "is_potentially_hazardous_asteroid": hazardous,
                    "close_approach_data": [
                        {
                            "close_approach_date": target_date,
                            "relative_velocity": {"kilometers_per_hour": "12345"},
                            "miss_distance": {"kilometers": "6789012"},
                            "orbiting_body": "Earth",
                        }
                    ],
                    "nasa_jpl_url": "https://jpl.example/A",
                }
            ]
        },
    }


@respx.mock
async def test_fetch_neo_cache_miss_writes_rows(db_session, nasa):
    respx.get("https://api.nasa.example/neo/rest/v1/feed").mock(
        return_value=httpx.Response(200, json=_payload("2020-05-01", hazardous=True)),
    )

    result = await neo_service.fetch_neo_feed(db_session, nasa, "2020-05-01", "2020-05-02")
    assert result.cached is False
    assert result.stale is False
    assert result.is_today is False
    assert len(result.rows) == 1
    row = result.rows[0]
    assert row.id == "2020-05-01-A"
    assert row.is_potentially_hazardous is True
    assert row.relative_velocity_kph == pytest.approx(12345.0)


async def test_fetch_neo_cache_hit_returns_without_upstream(db_session, nasa):
    db_session.add(
        Neo(
            id="cached-A",
            name="Cached A",
            close_approach_date="2020-06-01",
            is_potentially_hazardous=False,
            fetched_at=datetime(2020, 6, 1, 8, 0, 0),
        )
    )
    await db_session.commit()

    with respx.mock:
        route = respx.get("https://api.nasa.example/neo/rest/v1/feed")
        result = await neo_service.fetch_neo_feed(db_session, nasa, "2020-06-01", "2020-06-02")

    assert result.cached is True
    assert result.stale is False
    assert result.is_today is False
    assert route.called is False
    assert len(result.rows) == 1


@respx.mock
async def test_fetch_neo_stale_fallback(db_session, nasa):
    today = datetime.now(timezone.utc).date().isoformat()
    db_session.add(
        Neo(
            id="today-A",
            name="Today cached",
            close_approach_date=today,
            is_potentially_hazardous=False,
            fetched_at=datetime.utcnow() - timedelta(hours=1),
        )
    )
    await db_session.commit()

    respx.get("https://api.nasa.example/neo/rest/v1/feed").mock(
        return_value=httpx.Response(503),
    )

    result = await neo_service.fetch_neo_feed(db_session, nasa, today, today)
    assert result.cached is True
    assert result.stale is True
    assert result.is_today is True


@respx.mock
async def test_fetch_neo_upstream_error_no_cache_raises(db_session, nasa):
    respx.get("https://api.nasa.example/neo/rest/v1/feed").mock(
        return_value=httpx.Response(503),
    )

    with pytest.raises(NasaClientError):
        await neo_service.fetch_neo_feed(db_session, nasa, "2020-07-01", "2020-07-02")


@respx.mock
async def test_fetch_neo_upsert_updates_existing(db_session, nasa):
    today = datetime.now(timezone.utc).date().isoformat()
    # Pre-seed a row with the same id NASA will return, but different name
    db_session.add(
        Neo(
            id=f"{today}-A",
            name="Old name",
            close_approach_date=today,
            is_potentially_hazardous=False,
            fetched_at=datetime.utcnow() - timedelta(hours=6),
        )
    )
    await db_session.commit()

    respx.get("https://api.nasa.example/neo/rest/v1/feed").mock(
        return_value=httpx.Response(200, json=_payload(today, hazardous=True, name="Renamed")),
    )

    result = await neo_service.fetch_neo_feed(db_session, nasa, today, today)
    assert result.cached is False
    assert result.is_today is True

    updated = await db_session.get(Neo, f"{today}-A")
    assert updated is not None
    assert updated.name == "Renamed"
    assert updated.is_potentially_hazardous is True


async def test_fetch_neo_invalid_range_raises_valueerror(db_session, nasa):
    with pytest.raises(ValueError):
        await neo_service.fetch_neo_feed(db_session, nasa, "bad", "2020-01-02")

    with pytest.raises(ValueError):
        await neo_service.fetch_neo_feed(db_session, nasa, "2020-01-10", "2020-01-01")

    with pytest.raises(ValueError):
        await neo_service.fetch_neo_feed(db_session, nasa, "2020-01-01", "2020-01-20")


def test_neo_result_container_fields():
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    r = neo_service.NeoResult(rows=[], cached=True, stale=False, is_today=True, fetched_at=now)
    assert r.rows == []
    assert r.cached is True
    assert r.stale is False
    assert r.is_today is True
    assert r.fetched_at == now


def test_latest_fetched_at_empty_returns_now():
    before = datetime.now(timezone.utc)
    latest = neo_service._latest_fetched_at([])
    after = datetime.now(timezone.utc)
    assert before <= latest <= after


def test_validate_range_boundary_exact_seven_days():
    s, e = neo_service._validate_range("2020-01-01", "2020-01-07")
    assert (e - s).days == 6


def test_coerce_float_handles_various_types():
    assert neo_service._coerce_float(None) is None
    assert neo_service._coerce_float("12.5") == 12.5
    assert neo_service._coerce_float(3) == 3.0
    assert neo_service._coerce_float("nope") is None
    assert neo_service._coerce_float([1, 2]) is None


def test_neo_from_object_uses_feed_date_when_missing():
    obj = {"id": "X", "name": "X", "close_approach_data": []}
    row = neo_service._neo_from_object(obj, feed_date="2020-08-08")
    assert row.close_approach_date == "2020-08-08"
    assert row.miss_distance_km is None
    assert row.relative_velocity_kph is None


def test_range_includes_today_true_for_today():
    today = datetime.now(timezone.utc).date()
    assert neo_service._range_includes_today(today) is True


def test_range_includes_today_false_for_past():
    assert neo_service._range_includes_today(date(2000, 1, 1)) is False


@respx.mock
async def test_fetch_neo_handles_empty_near_earth_objects(db_session, nasa):
    respx.get("https://api.nasa.example/neo/rest/v1/feed").mock(
        return_value=httpx.Response(200, json={"element_count": 0, "near_earth_objects": {}}),
    )
    result = await neo_service.fetch_neo_feed(db_session, nasa, "2020-09-01", "2020-09-01")
    assert result.cached is False
    assert result.rows == []
    # _latest_fetched_at with empty rows still returns a datetime (now)
    assert isinstance(result.fetched_at, datetime)
