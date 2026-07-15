"""Tests for GET /api/v1/ephemerides/{slug}
(22-ephemeris-and-mission-replay.md — Foundation)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.models.ephemerides import Ephemeris, TrackedObject


async def _seed_tracked(db_session, spk_id="-170", slug="jwst", step_hours=24) -> TrackedObject:
    tracked = TrackedObject(
        spk_id=spk_id,
        slug=slug,
        name_key="spacecraft.jwst",
        kind="spacecraft",
        active=True,
        step_hours=step_hours,
    )
    db_session.add(tracked)
    await db_session.commit()
    return tracked


async def _seed_points(db_session, spk_id, start, n, step=timedelta(hours=24)) -> None:
    for i in range(n):
        db_session.add(
            Ephemeris(spk_id=spk_id, t_utc=start + step * i, x_au=float(i), y_au=float(i), z_au=float(i))
        )
    await db_session.commit()


async def test_get_ephemerides_returns_points_in_range(client, db_session):
    await _seed_tracked(db_session)
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    await _seed_points(db_session, "-170", start, 5)

    r = await client.get(
        "/api/v1/ephemerides/jwst",
        params={"from": "2024-01-01T00:00:00Z", "to": "2024-01-05T00:00:00Z"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["slug"] == "jwst"
    assert body["name_key"] == "spacecraft.jwst"
    assert len(body["points"]) == 5
    assert body["points"][0]["x"] == 0.0


async def test_get_ephemerides_sets_cache_control_header(client, db_session):
    await _seed_tracked(db_session)
    r = await client.get(
        "/api/v1/ephemerides/jwst",
        params={"from": "2024-01-01T00:00:00Z", "to": "2024-01-02T00:00:00Z"},
    )
    assert r.status_code == 200
    assert r.headers["cache-control"] == "public, max-age=3600"


async def test_get_ephemerides_unknown_slug_is_404(client, db_session):
    r = await client.get(
        "/api/v1/ephemerides/no-such-object",
        params={"from": "2024-01-01T00:00:00Z", "to": "2024-01-02T00:00:00Z"},
    )
    assert r.status_code == 404
    assert r.json()["detail"]["error"]["code"] == "UNKNOWN_OBJECT"


async def test_get_ephemerides_end_before_start_is_400(client, db_session):
    await _seed_tracked(db_session)
    r = await client.get(
        "/api/v1/ephemerides/jwst",
        params={"from": "2024-01-05T00:00:00Z", "to": "2024-01-01T00:00:00Z"},
    )
    assert r.status_code == 400
    assert r.json()["detail"]["error"]["code"] == "INVALID_RANGE"


async def test_get_ephemerides_range_too_wide_is_400(client, db_session):
    await _seed_tracked(db_session)
    r = await client.get(
        "/api/v1/ephemerides/jwst",
        params={"from": "2024-01-01T00:00:00Z", "to": "2024-06-01T00:00:00Z"},
    )
    assert r.status_code == 400
    assert r.json()["detail"]["error"]["code"] == "INVALID_RANGE"


async def test_get_ephemerides_defaults_to_trailing_window_when_omitted(client, db_session):
    """No from/to -> a `_DEFAULT_RANGE_DAYS`-day trailing window ending now,
    matching the worker's past-coverage window so a no-opinion caller gets a
    fully-cached response."""
    await _seed_tracked(db_session)
    now = datetime.now(timezone.utc)
    await _seed_points(db_session, "-170", now - timedelta(days=1), 2, step=timedelta(hours=12))

    r = await client.get("/api/v1/ephemerides/jwst")
    assert r.status_code == 200
    assert len(r.json()["points"]) == 2


async def test_get_ephemerides_naive_datetime_params_treated_as_utc(client, db_session):
    await _seed_tracked(db_session)
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    await _seed_points(db_session, "-170", start, 3)

    r = await client.get(
        "/api/v1/ephemerides/jwst",
        params={"from": "2024-01-01T00:00:00", "to": "2024-01-03T00:00:00"},
    )
    assert r.status_code == 200
    assert len(r.json()["points"]) == 3
