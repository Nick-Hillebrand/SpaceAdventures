"""Unit tests for launches_service helpers and sync edge branches."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from unittest.mock import AsyncMock

from datetime import timezone

from sqlalchemy import select

from app.models.launch_net_changes import LaunchNetChange
from app.models.launches import Launch
from app.services.launches_service import (
    _record_change,
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
        livestream_urls=[],
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
    stored = launch.translations_json
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
    assert launch.translations_json["de"]["mission_name"] == "DE:Starlink"


async def test_sync_retranslates_when_mission_changes(db_session):
    async def translator(fields):
        return {"de": {k: f"DE:{v}" for k, v in fields.items()}}

    await sync_launches(db_session, FakeLL2Client([_raw()]), translator=translator)

    updated = _raw()
    updated["mission"]["description"] = "New description."
    await sync_launches(db_session, FakeLL2Client([updated]), translator=translator)

    launch = await db_session.get(Launch, "l-1")
    assert launch.translations_json["de"]["mission_description"] == "DE:New description."


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


async def test_is_launches_table_empty(db_session):
    assert await is_launches_table_empty(db_session) is True
    await sync_launches(db_session, FakeLL2Client([_raw()]))
    assert await is_launches_table_empty(db_session) is False


# ---------------------------------------------------------------------------
# Slip-history recording (Step P4 / 18-slip-history-and-reliability.md §Stage 1)
# ---------------------------------------------------------------------------


def _net_dt(year: int, month: int, day: int, hour: int = 0) -> str:
    """Return an ISO-8601 UTC datetime string for use in raw LL2 fixtures."""
    return f"{year:04d}-{month:02d}-{day:02d}T{hour:02d}:00:00Z"


async def _all_changes(db_session) -> list[LaunchNetChange]:
    result = await db_session.execute(select(LaunchNetChange))
    return list(result.scalars().all())


async def test_net_slip_inserts_exactly_one_row(db_session):
    """A NET change beyond the 5-min threshold creates exactly one 'net' row."""
    await sync_launches(db_session, FakeLL2Client([_raw(net=_net_dt(2099, 7, 10, 12))]))
    # Slip by 1 hour — well above threshold
    await sync_launches(db_session, FakeLL2Client([_raw(net=_net_dt(2099, 7, 10, 13))]))
    changes = await _all_changes(db_session)
    assert len(changes) == 1
    c = changes[0]
    assert c.change_type == "net"
    assert c.launch_id == "l-1"
    assert c.provider_name == "SpaceX"
    assert c.rocket_name == "Falcon 9"
    assert c.pad_name == "SLC-40"
    assert "2099-07-10T12:00:00" in c.old_value
    assert "2099-07-10T13:00:00" in c.new_value


async def test_net_below_threshold_inserts_nothing(db_session):
    """A NET drift ≤ 5 minutes does not create a slip record."""
    await sync_launches(db_session, FakeLL2Client([_raw(net="2099-07-10T12:00:00Z")]))
    await sync_launches(db_session, FakeLL2Client([_raw(net="2099-07-10T12:04:00Z")]))
    assert await _all_changes(db_session) == []


async def test_status_change_inserts_row(db_session):
    """A status_abbrev change creates exactly one 'status' row."""
    await sync_launches(db_session, FakeLL2Client([_raw()]))
    updated = _raw(status={"abbrev": "Hold", "name": "Launch Hold"})
    await sync_launches(db_session, FakeLL2Client([updated]))
    changes = await _all_changes(db_session)
    assert len(changes) == 1
    c = changes[0]
    assert c.change_type == "status"
    assert c.old_value == "Go"
    assert c.new_value == "Hold"


async def test_unchanged_launch_inserts_nothing(db_session):
    """Syncing identical data twice produces no slip-history rows."""
    await sync_launches(db_session, FakeLL2Client([_raw()]))
    await sync_launches(db_session, FakeLL2Client([_raw()]))
    assert await _all_changes(db_session) == []


async def test_unsubscribed_launch_still_recorded(db_session):
    """Even launches with no subscribers get a slip-history row — record everything."""
    # No subscriptions are created, so PendingNotification rows would be 0.
    # Slip still gets recorded.
    await sync_launches(db_session, FakeLL2Client([_raw(net="2099-08-01T00:00:00Z")]))
    await sync_launches(db_session, FakeLL2Client([_raw(net="2099-08-02T00:00:00Z")]))
    changes = await _all_changes(db_session)
    assert len(changes) == 1
    assert changes[0].change_type == "net"


async def test_gone_flow_marks_not_deletes_history_persists(db_session):
    """Launches disappearing from LL2 are marked Gone (not deleted), and a
    'gone' slip-history row is written. Existing history rows persist because
    the launch row still exists (just with status_abbrev='Gone')."""
    await sync_launches(db_session, FakeLL2Client([_raw(ll2_id="l-1")]))
    # Second sync omits l-1 → should be marked Gone
    await sync_launches(db_session, FakeLL2Client([]))
    launch = await db_session.get(Launch, "l-1")
    assert launch is not None, "Gone launch must not be deleted from the launches table"
    assert launch.status_abbrev == "Gone"
    changes = await _all_changes(db_session)
    assert any(c.change_type == "gone" and c.launch_id == "l-1" for c in changes)


async def test_gone_from_empty_feed_records_gone_row(db_session):
    """When LL2 returns an empty feed, every non-Gone launch gets a 'gone' row."""
    await sync_launches(
        db_session,
        FakeLL2Client([_raw(ll2_id="l-1"), _raw(ll2_id="l-2")]),
    )
    await sync_launches(db_session, FakeLL2Client([]))
    changes = await _all_changes(db_session)
    gone_ids = {c.launch_id for c in changes if c.change_type == "gone"}
    assert gone_ids == {"l-1", "l-2"}


async def test_slip_history_sanitisation(db_session):
    """LL2-supplied strings with control characters are sanitised before storage."""
    malicious_agency = "Evil\r\nAgency"
    malicious_rocket = "Rocket\x00Name"
    raw = _raw(
        launch_service_provider={"name": malicious_agency, "type": "Commercial"},
        rocket={"configuration": {"name": malicious_rocket, "family": "F"}},
        status={"abbrev": "Hold\r\nInject", "name": "Hold"},
    )
    await sync_launches(db_session, FakeLL2Client([_raw()]))
    await sync_launches(db_session, FakeLL2Client([raw]))
    changes = await _all_changes(db_session)
    # At least one status change row was written (Go→Hold…)
    assert changes
    for c in changes:
        for field in (c.provider_name, c.rocket_name, c.old_value, c.new_value):
            if field:
                assert "\r" not in field
                assert "\n" not in field
                assert "\x00" not in field


async def test_record_change_helper_sanitises_and_adds(db_session):
    """_record_change directly: sanitises control chars, adds row in same transaction."""
    # We need a parent launch row for the FK to hold
    await sync_launches(db_session, FakeLL2Client([_raw()]))
    _record_change(
        db_session,
        launch_id="l-1",
        change_type="net",
        provider_name="Evil\r\nCorp",
        rocket_name="Rocket\x00\n",
        pad_name="Pad\r\n1",
        old_value="2099-01-01T00:00:00+00:00",
        new_value="2099-01-02T00:00:00+00:00",
    )
    await db_session.commit()
    changes = await _all_changes(db_session)
    net_rows = [c for c in changes if c.change_type == "net"]
    assert len(net_rows) == 1
    r = net_rows[0]
    assert "\r" not in r.provider_name and "\n" not in r.provider_name
    assert "\x00" not in r.rocket_name and "\n" not in r.rocket_name
    assert "\r" not in r.pad_name
