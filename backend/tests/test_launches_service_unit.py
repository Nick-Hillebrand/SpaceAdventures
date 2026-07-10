"""Unit tests for launches_service helpers and sync edge branches."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any
from unittest.mock import AsyncMock, patch

from sqlalchemy import select

from app.models.launches import Launch
from app.services import launches_service
from app.services.launches_service import (
    _extract_image_url,
    _translate_launch,
    _translation_fields,
    _trunc,
    _trunc_required,
    is_launches_table_empty,
    sync_launches,
)
from app.services.ll2_client import LL2ClientError


class FakeLL2Client:
    def __init__(self, launches: list[dict] | None = None, error: Exception | None = None):
        self._launches = launches or []
        self._error = error

    async def fetch_upcoming(self) -> list[dict[str, Any]]:
        if self._error is not None:
            raise self._error
        return self._launches


def _raw(ll2_id: str = "l-1", **overrides) -> dict:
    base = {
        "id": ll2_id,
        "name": "Falcon 9 | Starlink",
        "net": "2099-07-10T12:00:00Z",
        "status": {"abbrev": "Go", "name": "Go for Launch"},
        "launch_service_provider": {"name": "SpaceX", "type": "Commercial"},
        "rocket": {"configuration": {"name": "Falcon 9", "family": "Falcon"}},
        "mission": {"name": "Starlink", "description": "Sats.", "type": "Comms"},
        "pad": {"name": "SLC-40", "location": {"name": "Cape Canaveral"}},
        "image": "https://example.com/img.jpg",
        "vidURLs": [],
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


def test_trunc_branches():
    assert _trunc(None, 10) is None
    assert _trunc(42, 10) is None
    assert _trunc("x" * 20, 10) == "x" * 10


def test_trunc_required_branches():
    assert _trunc_required(None, 10) == ""
    assert _trunc_required(42, 10) == "42"
    assert _trunc_required("y" * 20, 10) == "y" * 10


def test_extract_image_url_forms():
    assert _extract_image_url("https://x.example/a.jpg") == "https://x.example/a.jpg"
    assert _extract_image_url("") is None
    assert _extract_image_url(None) is None
    assert _extract_image_url(42) is None
    assert (
        _extract_image_url({"image_url": "https://x.example/b.jpg"})
        == "https://x.example/b.jpg"
    )
    assert (
        _extract_image_url({"image_url": None, "thumbnail_url": "https://x.example/t.jpg"})
        == "https://x.example/t.jpg"
    )
    assert _extract_image_url({"image_url": None, "thumbnail_url": None}) is None


def _launch_row(**overrides) -> Launch:
    base = dict(
        ll2_id="l-1",
        name="Falcon 9",
        net=datetime(2099, 7, 10, 12, 0, 0),
        status_abbrev="Go",
        status_name="Go for Launch",
        agency_name="SpaceX",
        rocket_name="Falcon 9",
        mission_name="Starlink",
        mission_description="Sats.",
        pad_name="SLC-40",
        pad_location="Cape",
        livestream_urls="[]",
        fetched_at=datetime(2026, 1, 1),
    )
    base.update(overrides)
    return Launch(**base)


def test_translation_fields():
    launch = _launch_row()
    assert _translation_fields(launch) == {
        "mission_name": "Starlink",
        "mission_description": "Sats.",
    }
    empty = _launch_row(mission_name=None, mission_description=None)
    assert _translation_fields(empty) == {}


async def test_translate_launch_success():
    launch = _launch_row()

    async def translator(fields):
        return {"de": {k: f"DE:{v}" for k, v in fields.items()}}

    await _translate_launch(launch, translator)
    stored = json.loads(launch.translations_json)
    assert stored["de"]["mission_name"] == "DE:Starlink"


async def test_translate_launch_no_fields_noop():
    launch = _launch_row(mission_name=None, mission_description=None)
    translator = AsyncMock()
    await _translate_launch(launch, translator)
    translator.assert_not_awaited()
    assert launch.translations_json is None


async def test_translate_launch_failure_swallowed():
    launch = _launch_row()

    async def translator(fields):
        raise RuntimeError("translator down")

    await _translate_launch(launch, translator)
    assert launch.translations_json is None


# ---------------------------------------------------------------------------
# sync_launches edge branches
# ---------------------------------------------------------------------------


async def test_sync_ll2_error_leaves_db_untouched(db_session):
    client = FakeLL2Client(error=LL2ClientError("LL2_UNAVAILABLE", "down"))
    await sync_launches(db_session, client)
    result = await db_session.execute(select(Launch))
    assert result.scalars().all() == []


async def test_sync_truncates_at_100_launches(db_session):
    launches = [_raw(ll2_id=f"l-{i}") for i in range(105)]
    await sync_launches(db_session, FakeLL2Client(launches))
    result = await db_session.execute(select(Launch))
    assert len(result.scalars().all()) == 100


async def test_sync_skips_unparseable_and_idless_rows(db_session):
    launches = [
        _raw(ll2_id="good-1"),
        _raw(ll2_id="bad-net", net="not-a-date"),
        _raw(ll2_id=""),
    ]
    await sync_launches(db_session, FakeLL2Client(launches))
    result = await db_session.execute(select(Launch))
    ids = [row.ll2_id for row in result.scalars().all()]
    assert ids == ["good-1"]


async def test_sync_translates_new_launch(db_session):
    async def translator(fields):
        return {"de": {k: f"DE:{v}" for k, v in fields.items()}}

    await sync_launches(db_session, FakeLL2Client([_raw()]), translator=translator)
    launch = await db_session.get(Launch, "l-1")
    assert launch.translations_json is not None
    assert "DE:Starlink" in launch.translations_json


async def test_sync_retranslates_when_mission_changes(db_session):
    async def translator(fields):
        return {"de": {k: f"DE:{v}" for k, v in fields.items()}}

    await sync_launches(db_session, FakeLL2Client([_raw()]), translator=translator)

    updated = _raw()
    updated["mission"]["description"] = "New description."
    await sync_launches(db_session, FakeLL2Client([updated]), translator=translator)

    launch = await db_session.get(Launch, "l-1")
    assert "DE:New description." in launch.translations_json


async def test_sync_skips_translation_when_unchanged(db_session):
    calls = []

    async def translator(fields):
        calls.append(fields)
        return {"de": {k: v for k, v in fields.items()}}

    await sync_launches(db_session, FakeLL2Client([_raw()]), translator=translator)
    await sync_launches(db_session, FakeLL2Client([_raw()]), translator=translator)
    assert len(calls) == 1


async def test_sync_empty_feed_marks_all_gone(db_session):
    await sync_launches(db_session, FakeLL2Client([_raw()]))
    await sync_launches(db_session, FakeLL2Client([]))
    launch = await db_session.get(Launch, "l-1")
    assert launch.status_abbrev == "Gone"


async def test_sync_missing_launches_marked_gone(db_session):
    await sync_launches(db_session, FakeLL2Client([_raw(ll2_id="l-1"), _raw(ll2_id="l-2")]))
    await sync_launches(db_session, FakeLL2Client([_raw(ll2_id="l-2")]))
    gone = await db_session.get(Launch, "l-1")
    kept = await db_session.get(Launch, "l-2")
    assert gone.status_abbrev == "Gone"
    assert kept.status_abbrev == "Go"


async def test_sync_with_settings_drains_queue(db_session, settings):
    drain = AsyncMock()
    with patch.object(launches_service.notification_service, "drain_queue", drain) if hasattr(
        launches_service, "notification_service"
    ) else patch("app.services.notification_service.drain_queue", drain):
        await sync_launches(db_session, FakeLL2Client([_raw()]), settings=settings)
    drain.assert_awaited_once()


async def test_is_launches_table_empty(db_session):
    assert await is_launches_table_empty(db_session) is True
    await sync_launches(db_session, FakeLL2Client([_raw()]))
    assert await is_launches_table_empty(db_session) is False
