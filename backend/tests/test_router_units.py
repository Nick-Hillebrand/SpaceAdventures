"""Direct-call unit tests for apod/launches router helpers and handlers.

Complements test_router_coverage.py — direct calls force correct coverage
attribution for branches the ASGI-level tests miss.
"""

from __future__ import annotations

import json
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from app.models.apod import Apod
from app.models.launches import Launch
from app.routers.apod import _apply_translations, _get_nasa_client, _get_translator, get_apod
from app.routers.launches import (
    _apply_launch_translations,
    _get_ll2_client,
    get_upcoming_launches,
    sync_launches,
)
from app.schemas.apod import ApodData
from app.schemas.launches import LaunchOut


def _bare_request() -> SimpleNamespace:
    """A request whose app.state has no registered clients."""
    return SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace()))


# ---------------------------------------------------------------------------
# APOD router
# ---------------------------------------------------------------------------


def test_apod_client_dep_missing_returns_503():
    with pytest.raises(HTTPException) as exc_info:
        _get_nasa_client(_bare_request())
    assert exc_info.value.status_code == 503


def test_apod_translator_dep_missing_returns_none():
    assert _get_translator(_bare_request()) is None


def _apod_data() -> ApodData:
    return ApodData(
        date="2026-01-01",
        title="Sun",
        explanation="A star.",
        url="https://apod.nasa.gov/x.jpg",
        media_type="image",
    )


def test_apod_apply_translations_english_passthrough():
    data = _apod_data()
    assert _apply_translations(data, '{"de": {"title": "Sonne"}}', "en") is data


def test_apod_apply_translations_no_json_passthrough():
    data = _apod_data()
    assert _apply_translations(data, None, "de") is data


def test_apod_apply_translations_missing_lang_passthrough():
    data = _apod_data()
    translations = json.dumps({"fr": {"title": "Soleil"}})
    assert _apply_translations(data, translations, "de") is data


def test_apod_apply_translations_applies_lang():
    data = _apod_data()
    translations = json.dumps({"de": {"title": "Sonne", "explanation": "Ein Stern."}})
    result = _apply_translations(data, translations, "de")
    assert result.title == "Sonne"
    assert result.explanation == "Ein Stern."


def test_apod_apply_translations_partial_lang_keeps_missing_fields():
    data = _apod_data()
    translations = json.dumps({"de": {"title": "Sonne"}})
    result = _apply_translations(data, translations, "de")
    assert result.title == "Sonne"
    assert result.explanation == "A star."


def test_apod_apply_translations_invalid_json_passthrough():
    data = _apod_data()
    assert _apply_translations(data, "{not json", "de") is data


def _apod_row(translations_json: str | None = None) -> Apod:
    return Apod(
        date="2026-01-01",
        title="Sun",
        explanation="A star.",
        url="https://apod.nasa.gov/x.jpg",
        media_type="image",
        fetched_at=datetime(2026, 1, 1, 0, 0, 0),
        translations_json=translations_json,
    )


async def test_get_apod_route_returns_translated_payload(db_session):
    row = _apod_row(json.dumps({"de": {"title": "Sonne", "explanation": "Ein Stern."}}))
    fake_result = SimpleNamespace(row=row, cached=True, stale=False, is_today=False)
    with patch(
        "app.services.apod_service.fetch_apod", AsyncMock(return_value=fake_result)
    ):
        response = await get_apod(
            date="2026-01-01",
            lang="de",
            session=db_session,
            client=MagicMock(),
            translator=None,
        )
    assert response.data.title == "Sonne"
    assert response.cached is True


async def test_get_apod_route_defaults_to_today(db_session):
    fake_result = SimpleNamespace(row=_apod_row(), cached=False, stale=False, is_today=True)
    fetch = AsyncMock(return_value=fake_result)
    with patch("app.services.apod_service.fetch_apod", fetch):
        response = await get_apod(
            date=None, lang="en", session=db_session, client=MagicMock(), translator=None
        )
    assert response.is_today is True
    target_date = fetch.await_args.args[2]
    assert target_date == datetime.now().date().isoformat() or len(target_date) == 10


async def test_get_apod_route_invalid_date_400(db_session):
    with patch(
        "app.services.apod_service.fetch_apod", AsyncMock(side_effect=ValueError("bad"))
    ):
        with pytest.raises(HTTPException) as exc_info:
            await get_apod(
                date="not-a-date",
                lang="en",
                session=db_session,
                client=MagicMock(),
                translator=None,
            )
    assert exc_info.value.status_code == 400


# ---------------------------------------------------------------------------
# Launches router
# ---------------------------------------------------------------------------


def test_ll2_client_dep_missing_returns_503():
    with pytest.raises(HTTPException) as exc_info:
        _get_ll2_client(_bare_request())
    assert exc_info.value.status_code == 503


def _launch_out(**overrides) -> LaunchOut:
    base = dict(
        ll2_id="l-1",
        name="Falcon 9 | Starlink",
        net=datetime(2026, 7, 10, 12, 0, 0),
        status_abbrev="Go",
        status_name="Go for Launch",
        agency_name="SpaceX",
        agency_type="Commercial",
        rocket_name="Falcon 9",
        rocket_family="Falcon",
        mission_name="Starlink",
        mission_description="Sats.",
        mission_type="Communications",
        pad_name="SLC-40",
        pad_location="Cape Canaveral",
        image_url=None,
        livestream_urls=[],
        fetched_at=datetime(2026, 1, 1),
    )
    base.update(overrides)
    return LaunchOut.model_validate(base)


def test_launch_apply_translations_english_passthrough():
    out = _launch_out()
    assert _apply_launch_translations(out, '{"de": {"mission_name": "X"}}', "en") is out


def test_launch_apply_translations_no_json_passthrough():
    out = _launch_out()
    assert _apply_launch_translations(out, None, "de") is out


def test_launch_apply_translations_missing_lang_passthrough():
    out = _launch_out()
    translations = json.dumps({"fr": {"mission_name": "Mission FR"}})
    assert _apply_launch_translations(out, translations, "de") is out


def test_launch_apply_translations_applies_fields():
    out = _launch_out()
    translations = json.dumps(
        {"de": {"mission_name": "Starlink DE", "mission_description": "Satelliten."}}
    )
    result = _apply_launch_translations(out, translations, "de")
    assert result.mission_name == "Starlink DE"
    assert result.mission_description == "Satelliten."


def test_launch_apply_translations_empty_values_ignored():
    out = _launch_out()
    translations = json.dumps({"de": {"mission_name": "", "mission_description": ""}})
    assert _apply_launch_translations(out, translations, "de") is out


def test_launch_apply_translations_invalid_json_passthrough():
    out = _launch_out()
    assert _apply_launch_translations(out, "{broken", "de") is out


def _launch_row(ll2_id: str = "l-1", translations_json: str | None = None) -> Launch:
    return Launch(
        ll2_id=ll2_id,
        name="Falcon 9 | Starlink",
        net=datetime(2099, 7, 10, 12, 0, 0),
        status_abbrev="Go",
        status_name="Go for Launch",
        agency_name="SpaceX",
        rocket_name="Falcon 9",
        mission_name="Starlink",
        mission_description="Sats.",
        pad_name="SLC-40",
        pad_location="Cape Canaveral",
        livestream_urls="[]",
        fetched_at=datetime(2026, 1, 1),
        translations_json=translations_json,
    )


async def test_get_upcoming_launches_route_translates(db_session):
    db_session.add(
        _launch_row(
            translations_json=json.dumps({"de": {"mission_name": "Starlink DE"}})
        )
    )
    await db_session.commit()

    response = await get_upcoming_launches(lang="de", session=db_session)
    assert response.data[0].mission_name == "Starlink DE"
    assert response.cached is True


async def test_get_upcoming_launches_route_english(db_session):
    db_session.add(_launch_row())
    await db_session.commit()

    response = await get_upcoming_launches(lang="en", session=db_session)
    assert response.data[0].mission_name == "Starlink"


async def test_sync_launches_route_calls_service(db_session):
    sync_mock = AsyncMock()
    ll2_client = MagicMock()
    with patch("app.services.launches_service.sync_launches", sync_mock):
        result = await sync_launches(
            session=db_session, ll2_client=ll2_client, translator=None, _admin=None
        )
    assert result == {"status": "ok"}
    sync_mock.assert_awaited_once()
