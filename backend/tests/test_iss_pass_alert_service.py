"""Tests for iss_pass_alert_service — pass_precompute/pass_notify job bodies
(20-location-and-sky-alerts.md L1)."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import httpx
import pytest
import respx
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.iss_pass_alert import IssPassAlert
from app.models.notification_log import PendingNotification
from app.models.subscription import Subscription
from app.models.user import User
from app.services import iss_pass_alert_service

_N2YO_BASE = "https://api.n2yo.example/rest/v1/satellite"
_PWD = CryptContext(schemes=["bcrypt"], deprecated="auto")


def _make_user(
    session: AsyncSession,
    email: str,
    is_pro: bool = True,
    lat: float | None = 48.86,
    lng: float | None = 2.35,
    tz: str | None = "Europe/Paris",
) -> User:
    user = User(
        first_name="Pro",
        last_name="User",
        email=email,
        password_hash=_PWD.hash("pw"),
        email_verified=True,
        is_pro=is_pro,
        location_lat=lat,
        location_lng=lng,
        location_tz=tz,
        location_name="Paris" if lat is not None else None,
    )
    session.add(user)
    return user


async def _make_iss_pass_subscription(session: AsyncSession, user_id: int, **kwargs) -> Subscription:
    sub = Subscription(
        user_id=user_id,
        type="iss_pass",
        notify_push=kwargs.get("notify_push", True),
        notify_email=kwargs.get("notify_email", False),
    )
    session.add(sub)
    await session.flush()
    return sub


def _visual_pass(start: datetime, max_el: float = 45.0, start_az: float = 270.0, end_az: float = 90.0) -> dict:
    end = start + timedelta(minutes=4)
    return {
        "startUTC": int(start.timestamp()),
        "maxUTC": int(start.timestamp()) + 120,
        "endUTC": int(end.timestamp()),
        "startAz": start_az,
        "startAzCompass": "W",
        "endAz": end_az,
        "endAzCompass": "E",
        "maxEl": max_el,
        "mag": -2.5,
        "duration": 240,
    }


# ---------------------------------------------------------------------------
# _parse_pass / _safe_float — untrusted upstream data (rule 9)
# ---------------------------------------------------------------------------


def test_parse_pass_valid():
    start = datetime(2026, 7, 15, 20, 0, tzinfo=timezone.utc)
    parsed = iss_pass_alert_service._parse_pass(_visual_pass(start))
    assert parsed is not None
    assert parsed["max_el"] == 45.0
    assert parsed["start_az"] == 270.0
    assert parsed["end_az"] == 90.0
    assert parsed["mag"] == -2.5


@pytest.mark.parametrize("missing_key", ["startUTC", "endUTC", "maxEl", "startAz", "endAz"])
def test_parse_pass_skips_missing_required_field(missing_key):
    start = datetime(2026, 7, 15, 20, 0, tzinfo=timezone.utc)
    raw = _visual_pass(start)
    del raw[missing_key]
    assert iss_pass_alert_service._parse_pass(raw) is None


def test_parse_pass_skips_non_numeric_field():
    start = datetime(2026, 7, 15, 20, 0, tzinfo=timezone.utc)
    raw = _visual_pass(start)
    raw["maxEl"] = "not-a-number"
    assert iss_pass_alert_service._parse_pass(raw) is None


def test_parse_pass_mag_optional_and_defensive():
    start = datetime(2026, 7, 15, 20, 0, tzinfo=timezone.utc)
    raw = _visual_pass(start)
    del raw["mag"]
    parsed = iss_pass_alert_service._parse_pass(raw)
    assert parsed is not None
    assert parsed["mag"] is None

    raw["mag"] = "garbage"
    parsed = iss_pass_alert_service._parse_pass(raw)
    assert parsed["mag"] is None


def test_safe_float():
    assert iss_pass_alert_service._safe_float(None) is None
    assert iss_pass_alert_service._safe_float("not-a-number") is None
    assert iss_pass_alert_service._safe_float("1.5") == 1.5
    assert iss_pass_alert_service._safe_float(2) == 2.0


@pytest.mark.parametrize(
    "bad_field",
    [
        "<script>alert(1)</script>",
        "'; DROP TABLE iss_pass_alerts; --",
        "{{7*7}}",
        "not-a-number",
        "",
    ],
)
def test_parse_pass_rejects_injection_shaped_numeric_fields(bad_field):
    """N2YO's visualpasses response is untrusted upstream input (rule 9,
    25-security-testing.md §2.3) — every stored field is numeric
    (start/end timestamps, elevation, azimuths, magnitude), so the relevant
    control is that a non-numeric field (including injection-shaped
    strings) makes the whole row skipped via `_parse_pass` returning None,
    never coerced or partially stored. No string-typed N2YO field ever
    reaches storage or an output context (HTML/ICS/SEO-meta/JSON-LD/SMS/
    social) — like Horizons (see test_horizons_client.py and
    test_injection.py's module docstring), this source is out of scope for
    the fixture-payload matrix and covered here instead."""
    start = datetime(2026, 7, 15, 20, 0, tzinfo=timezone.utc)
    raw = _visual_pass(start)
    raw["maxEl"] = bad_field
    assert iss_pass_alert_service._parse_pass(raw) is None

    raw2 = _visual_pass(start)
    raw2["startAz"] = bad_field
    assert iss_pass_alert_service._parse_pass(raw2) is None

    raw3 = _visual_pass(start)
    raw3["mag"] = bad_field
    parsed = iss_pass_alert_service._parse_pass(raw3)
    assert parsed is not None
    assert parsed["mag"] is None


# ---------------------------------------------------------------------------
# _eligible_locations
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_eligible_locations_groups_by_rounded_coordinate(db_session):
    u1 = _make_user(db_session, "u1@example.com", is_pro=True, lat=48.86, lng=2.35)
    u2 = _make_user(db_session, "u2@example.com", is_pro=True, lat=48.86, lng=2.35)
    u3 = _make_user(db_session, "u3@example.com", is_pro=True, lat=40.71, lng=-74.01)
    await db_session.flush()
    for u in (u1, u2, u3):
        await _make_iss_pass_subscription(db_session, u.id)
    await db_session.commit()

    groups = await iss_pass_alert_service._eligible_locations(db_session)
    assert set(groups.keys()) == {(48.86, 2.35), (40.71, -74.01)}
    assert len(groups[(48.86, 2.35)]) == 2
    assert len(groups[(40.71, -74.01)]) == 1


@pytest.mark.asyncio
async def test_eligible_locations_excludes_free_users(db_session):
    free_user = _make_user(db_session, "free@example.com", is_pro=False)
    await db_session.flush()
    await _make_iss_pass_subscription(db_session, free_user.id)
    await db_session.commit()

    groups = await iss_pass_alert_service._eligible_locations(db_session)
    assert groups == {}


@pytest.mark.asyncio
async def test_eligible_locations_excludes_users_without_location(db_session):
    user = _make_user(db_session, "nolo@example.com", is_pro=True, lat=None, lng=None)
    await db_session.flush()
    await _make_iss_pass_subscription(db_session, user.id)
    await db_session.commit()

    groups = await iss_pass_alert_service._eligible_locations(db_session)
    assert groups == {}


@pytest.mark.asyncio
async def test_eligible_locations_excludes_pro_users_without_subscription(db_session):
    _make_user(db_session, "nosub@example.com", is_pro=True)
    await db_session.commit()

    groups = await iss_pass_alert_service._eligible_locations(db_session)
    assert groups == {}


# ---------------------------------------------------------------------------
# precompute_passes
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@respx.mock
async def test_precompute_batches_shared_coordinate_into_one_call(db_session, settings):
    from app.services.n2yo_client import N2YOClient

    u1 = _make_user(db_session, "u1@example.com")
    u2 = _make_user(db_session, "u2@example.com")
    u3 = _make_user(db_session, "u3@example.com")
    await db_session.flush()
    for u in (u1, u2, u3):
        await _make_iss_pass_subscription(db_session, u.id)
    await db_session.commit()

    start = datetime.now(timezone.utc) + timedelta(hours=1)
    route = respx.get(f"{_N2YO_BASE}/visualpasses/25544/48.86/2.35/0.0/2/120").mock(
        return_value=httpx.Response(200, json={"passes": [_visual_pass(start)]})
    )
    client = N2YOClient(settings)
    try:
        await iss_pass_alert_service.precompute_passes(db_session, client, cap=900)
    finally:
        await client.close()

    assert route.call_count == 1
    result = await db_session.execute(select(IssPassAlert))
    rows = list(result.scalars().all())
    assert len(rows) == 3
    assert {r.user_id for r in rows} == {u1.id, u2.id, u3.id}


@pytest.mark.asyncio
@respx.mock
async def test_precompute_stops_cleanly_on_quota_exhaustion(db_session, settings):
    from app.models import N2yoQuota
    from app.services.n2yo_client import N2YOClient

    u1 = _make_user(db_session, "u1@example.com")
    await db_session.flush()
    await _make_iss_pass_subscription(db_session, u1.id)
    db_session.add(N2yoQuota(id=1, window_start=datetime.now(timezone.utc), used=900))
    await db_session.commit()

    route = respx.get(f"{_N2YO_BASE}/visualpasses/25544/48.86/2.35/0.0/2/120")
    client = N2YOClient(settings)
    try:
        await iss_pass_alert_service.precompute_passes(db_session, client, cap=900)
    finally:
        await client.close()

    assert not route.called
    result = await db_session.execute(select(IssPassAlert))
    assert list(result.scalars().all()) == []


@pytest.mark.asyncio
@respx.mock
async def test_precompute_continues_past_n2yo_error_for_one_batch(db_session, settings):
    from app.services.n2yo_client import N2YOClient

    u1 = _make_user(db_session, "u1@example.com", lat=48.86, lng=2.35)
    u2 = _make_user(db_session, "u2@example.com", lat=40.71, lng=-74.01)
    await db_session.flush()
    await _make_iss_pass_subscription(db_session, u1.id)
    await _make_iss_pass_subscription(db_session, u2.id)
    await db_session.commit()

    respx.get(f"{_N2YO_BASE}/visualpasses/25544/48.86/2.35/0.0/2/120").mock(
        return_value=httpx.Response(200, json={"error": "boom"})
    )
    start = datetime.now(timezone.utc) + timedelta(hours=1)
    respx.get(f"{_N2YO_BASE}/visualpasses/25544/40.71/-74.01/0.0/2/120").mock(
        return_value=httpx.Response(200, json={"passes": [_visual_pass(start)]})
    )
    client = N2YOClient(settings)
    try:
        await iss_pass_alert_service.precompute_passes(db_session, client, cap=900)
    finally:
        await client.close()

    result = await db_session.execute(select(IssPassAlert))
    rows = list(result.scalars().all())
    assert len(rows) == 1
    assert rows[0].user_id == u2.id


@pytest.mark.asyncio
@respx.mock
async def test_precompute_skips_malformed_passes(db_session, settings):
    from app.services.n2yo_client import N2YOClient

    u1 = _make_user(db_session, "u1@example.com")
    await db_session.flush()
    await _make_iss_pass_subscription(db_session, u1.id)
    await db_session.commit()

    start = datetime.now(timezone.utc) + timedelta(hours=1)
    good = _visual_pass(start)
    bad = _visual_pass(start + timedelta(hours=5))
    del bad["maxEl"]
    respx.get(f"{_N2YO_BASE}/visualpasses/25544/48.86/2.35/0.0/2/120").mock(
        return_value=httpx.Response(200, json={"passes": [good, bad]})
    )
    client = N2YOClient(settings)
    try:
        await iss_pass_alert_service.precompute_passes(db_session, client, cap=900)
    finally:
        await client.close()

    result = await db_session.execute(select(IssPassAlert))
    assert len(list(result.scalars().all())) == 1


@pytest.mark.asyncio
@respx.mock
async def test_precompute_upserts_existing_pass(db_session, settings):
    from app.services.n2yo_client import N2YOClient

    u1 = _make_user(db_session, "u1@example.com")
    await db_session.flush()
    await _make_iss_pass_subscription(db_session, u1.id)
    await db_session.commit()

    start = datetime.now(timezone.utc).replace(microsecond=0) + timedelta(hours=1)
    respx.get(f"{_N2YO_BASE}/visualpasses/25544/48.86/2.35/0.0/2/120").mock(
        return_value=httpx.Response(200, json={"passes": [_visual_pass(start, max_el=30.0)]})
    )
    client = N2YOClient(settings)
    try:
        await iss_pass_alert_service.precompute_passes(db_session, client, cap=900)

        respx.routes.clear()
        respx.get(f"{_N2YO_BASE}/visualpasses/25544/48.86/2.35/0.0/2/120").mock(
            return_value=httpx.Response(200, json={"passes": [_visual_pass(start, max_el=60.0)]})
        )
        await iss_pass_alert_service.precompute_passes(db_session, client, cap=900)
    finally:
        await client.close()

    result = await db_session.execute(select(IssPassAlert))
    rows = list(result.scalars().all())
    assert len(rows) == 1
    assert rows[0].max_el == 60.0


# ---------------------------------------------------------------------------
# notify_passes
# ---------------------------------------------------------------------------


async def _make_alert(session: AsyncSession, user_id: int, start_utc: datetime, max_el: float = 45.0) -> IssPassAlert:
    alert = IssPassAlert(
        user_id=user_id,
        start_utc=start_utc,
        end_utc=start_utc + timedelta(minutes=4),
        max_el=max_el,
        start_az=270.0,
        end_az=90.0,
        mag=-2.5,
        notified=False,
    )
    session.add(alert)
    await session.flush()
    return alert


@pytest.mark.asyncio
async def test_notify_passes_selects_within_window_and_enqueues(db_session):
    user = _make_user(db_session, "u1@example.com")
    await db_session.flush()
    sub = await _make_iss_pass_subscription(db_session, user.id)
    now = datetime.now(timezone.utc)
    alert = await _make_alert(db_session, user.id, now + timedelta(minutes=30))
    await db_session.commit()

    await iss_pass_alert_service.notify_passes(db_session)

    await db_session.refresh(alert)
    assert alert.notified is True

    result = await db_session.execute(select(PendingNotification))
    pending = list(result.scalars().all())
    assert len(pending) == 1
    assert pending[0].change_type == "ISS_PASS"
    assert pending[0].iss_pass_alert_id == alert.id
    assert pending[0].subscription_id == sub.id


@pytest.mark.asyncio
@pytest.mark.parametrize("minutes_out", [24, 36])
async def test_notify_passes_window_boundaries_not_selected(db_session, minutes_out):
    user = _make_user(db_session, "u1@example.com")
    await db_session.flush()
    await _make_iss_pass_subscription(db_session, user.id)
    now = datetime.now(timezone.utc)
    alert = await _make_alert(db_session, user.id, now + timedelta(minutes=minutes_out))
    await db_session.commit()

    await iss_pass_alert_service.notify_passes(db_session)

    await db_session.refresh(alert)
    assert alert.notified is False
    result = await db_session.execute(select(PendingNotification))
    assert list(result.scalars().all()) == []


@pytest.mark.asyncio
async def test_notify_passes_elevation_floor(db_session):
    user = _make_user(db_session, "u1@example.com")
    await db_session.flush()
    await _make_iss_pass_subscription(db_session, user.id)
    now = datetime.now(timezone.utc)
    alert = await _make_alert(db_session, user.id, now + timedelta(minutes=30), max_el=24.9)
    await db_session.commit()

    await iss_pass_alert_service.notify_passes(db_session)

    await db_session.refresh(alert)
    assert alert.notified is False
    result = await db_session.execute(select(PendingNotification))
    assert list(result.scalars().all()) == []


@pytest.mark.asyncio
async def test_notify_passes_skips_already_notified(db_session):
    user = _make_user(db_session, "u1@example.com")
    await db_session.flush()
    await _make_iss_pass_subscription(db_session, user.id)
    now = datetime.now(timezone.utc)
    alert = await _make_alert(db_session, user.id, now + timedelta(minutes=30))
    alert.notified = True
    await db_session.commit()

    await iss_pass_alert_service.notify_passes(db_session)

    result = await db_session.execute(select(PendingNotification))
    assert list(result.scalars().all()) == []


@pytest.mark.asyncio
async def test_notify_passes_no_op_when_subscription_gone(db_session):
    """User unsubscribed after precompute — alert still gets claimed
    (notified=True, no double-processing on the next run) but nothing enqueues."""
    user = _make_user(db_session, "u1@example.com")
    await db_session.flush()
    now = datetime.now(timezone.utc)
    alert = await _make_alert(db_session, user.id, now + timedelta(minutes=30))
    await db_session.commit()

    await iss_pass_alert_service.notify_passes(db_session)

    await db_session.refresh(alert)
    assert alert.notified is True
    result = await db_session.execute(select(PendingNotification))
    assert list(result.scalars().all()) == []


@pytest.mark.postgres_only
@pytest.mark.asyncio
async def test_notify_passes_no_double_enqueue_on_concurrent_runs(db_engine):
    """Requires Postgres row locking (17-worker-and-scheduling.md P3.3) —
    the UPDATE...WHERE notified=False claim must serialize two concurrent
    pass_notify runs so exactly one enqueues the notification."""
    factory = async_sessionmaker(db_engine, expire_on_commit=False, class_=AsyncSession)

    async with factory() as setup_session:
        user = _make_user(setup_session, "race@example.com")
        await setup_session.flush()
        await _make_iss_pass_subscription(setup_session, user.id)
        now = datetime.now(timezone.utc)
        await _make_alert(setup_session, user.id, now + timedelta(minutes=30))
        await setup_session.commit()

    async def _run():
        async with factory() as session:
            await iss_pass_alert_service.notify_passes(session)

    await asyncio.gather(_run(), _run())

    async with factory() as check_session:
        result = await check_session.execute(select(PendingNotification))
        assert len(list(result.scalars().all())) == 1
