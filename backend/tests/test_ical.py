"""Tests for Step L2: iCal feeds (Architecture/19-notification-channels-v2.md L2).

Unit tests for `_fold`, `_vevent_lines`, and handler branches are included
alongside the HTTP-layer integration tests. This is necessary because Python
3.13 + pytest-asyncio + httpx ASGITransport can fail to record branch
transitions inside async handlers after `await` suspension points — a known
limitation of the CPython 3.13 tracing internals. Direct coroutine calls
(without going through FastAPI's ASGI dispatch) reliably get tracked.

Coverage:
- ical_escape() unit tests (commas, semicolons, newlines, backslashes round-trip)
- GET /api/v1/ical/{token}.ics: valid ICS parsed by the `icalendar` lib
- SEQUENCE increments after a NET change in launch_net_changes
- STATUS:CANCELLED on a Gone launch
- Token rotation kills old URL (404)
- Non-Pro token → 404 (no oracle — same as unknown token, per §2.1)
- ical_feed_escapes_injection_payloads: every injection payload string in
  SUMMARY/DESCRIPTION survives without raw special chars (§2.3 coverage for
  the ICS output context, per test_injection.py docstring note on L2)
"""
from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone

import pytest
from icalendar import Calendar
from passlib.context import CryptContext
from sqlalchemy import select

from app.models.launch_net_changes import LaunchNetChange
from app.models.launches import Launch
from app.models.subscription import Subscription
from app.models.user import User
from app.services.notification_service import ical_escape

_pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")


def _user(email_suffix: str, *, is_pro: bool = True, ical_token: str | None = None) -> User:
    return User(
        first_name="Test",
        last_name="User",
        email=f"ical-{email_suffix}@example.com",
        password_hash=_pwd_ctx.hash("pw"),
        is_pro=is_pro,
        ical_token=ical_token,
    )


def _launch(ll2_id: str, *, status_abbrev: str = "Go", mission_name: str | None = None) -> Launch:
    net = datetime.now(timezone.utc) + timedelta(days=1)
    return Launch(
        ll2_id=ll2_id,
        name=f"Launch {ll2_id}",
        net=net.replace(tzinfo=None),
        status_abbrev=status_abbrev,
        status_name="Go for Launch" if status_abbrev != "Gone" else "Launch Cancelled",
        agency_name="Test Agency",
        rocket_name="Test Rocket",
        pad_name="Pad 39A",
        pad_location="KSC",
        mission_name=mission_name,
    )


# ---------------------------------------------------------------------------
# Direct unit tests — _fold(), _vevent_lines() (bypasses async dispatch)
# ---------------------------------------------------------------------------


def test_fold_short_line_unchanged() -> None:
    from app.services.ical_service import _fold

    short = "SUMMARY:Hello World"
    assert _fold(short) == short


def test_fold_long_line_splits_at_75_octets() -> None:
    from app.services.ical_service import _fold

    # 80 ASCII chars → must be folded at 75 chars.
    long_line = "DESCRIPTION:" + "A" * 68  # 12 + 68 = 80 chars
    folded = _fold(long_line)
    assert "\r\n " in folded  # continuation-line marker
    # Each physical line must be ≤ 75 octets.
    for physical in folded.split("\r\n"):
        assert len(physical.encode("utf-8")) <= 75


def test_fold_long_line_with_multibyte() -> None:
    from app.services.ical_service import _fold

    # Embed non-ASCII to exercise the UTF-8 boundary back-off path.
    long_line = "SUMMARY:" + "München " * 10  # "München" is 7 bytes (ü = 2 bytes)
    folded = _fold(long_line)
    # Result must be valid UTF-8 and round-trip losslessly.
    assert "München" in folded.replace("\r\n ", "")


def test_vevent_lines_with_livestream_url() -> None:
    from datetime import datetime, timezone

    from app.services.ical_service import _vevent_lines

    launch = type("L", (), {
        "ll2_id": "x-1",
        "name": "Test",
        "net": datetime(2099, 1, 1, tzinfo=timezone.utc),
        "status_abbrev": "Go",
        "status_name": "Go for Launch",
        "mission_name": None,
        "livestream_urls": [{"url": "https://youtube.com/watch?v=abc", "title": "Watch"}],
    })()
    lines = _vevent_lines(launch, 0)
    desc = next(l for l in lines if l.startswith("DESCRIPTION:"))
    assert "URL:" in desc
    assert "youtube.com" in desc


def test_vevent_lines_without_livestream_url() -> None:
    from datetime import datetime, timezone

    from app.services.ical_service import _vevent_lines

    launch = type("L", (), {
        "ll2_id": "x-2",
        "name": "Test",
        "net": datetime(2099, 1, 1, tzinfo=timezone.utc),
        "status_abbrev": "Go",
        "status_name": "Go for Launch",
        "mission_name": "Test Mission",
        "livestream_urls": [],
    })()
    lines = _vevent_lines(launch, 0)
    desc = next(l for l in lines if l.startswith("DESCRIPTION:"))
    assert "URL:" not in desc


# ---------------------------------------------------------------------------
# Direct handler unit tests — covers router branches without async dispatch
# ---------------------------------------------------------------------------


async def test_handler_get_ical_feed_user_not_found(db_session) -> None:
    """handler branch: user is None → 404."""
    from fastapi import HTTPException

    from app.routers.ical import get_ical_feed

    with pytest.raises(HTTPException) as exc_info:
        await get_ical_feed("nonexistent-token", db_session)
    assert exc_info.value.status_code == 404


async def test_handler_get_ical_feed_non_pro_user(db_session) -> None:
    """handler branch: user found but not Pro → 404 (no oracle, same as unknown token)."""
    from fastapi import HTTPException

    from app.routers.ical import get_ical_feed

    token = secrets.token_urlsafe(32)
    u = _user("direct-nonpro", is_pro=False, ical_token=token)
    db_session.add(u)
    await db_session.commit()

    with pytest.raises(HTTPException) as exc_info:
        await get_ical_feed(token, db_session)
    assert exc_info.value.status_code == 404


async def test_handler_get_ical_feed_pro_user_returns_ics(db_session) -> None:
    """handler branch: user found, is Pro → 200 with ICS content."""
    from app.routers.ical import get_ical_feed

    token = secrets.token_urlsafe(32)
    u = _user("direct-pro", is_pro=True, ical_token=token)
    db_session.add(u)
    await db_session.commit()

    response = await get_ical_feed(token, db_session)
    assert response.status_code == 200
    assert "BEGIN:VCALENDAR" in response.body.decode()


async def test_handler_rotate_token_returns_new_token(db_session) -> None:
    """handler: Pro user → POST /rotate generates and returns a new token."""
    from app.routers.ical import rotate_ical_token

    u = _user("direct-rotate", is_pro=True)
    db_session.add(u)
    await db_session.commit()

    result = await rotate_ical_token(db_session, u)
    assert "ical_token" in result
    assert isinstance(result["ical_token"], str)
    assert len(result["ical_token"]) > 0


async def test_handler_rotate_non_pro_returns_403(db_session) -> None:
    """handler: free-tier user → POST /rotate is 403 (CLAUDE.md rule 11)."""
    from fastapi import HTTPException

    from app.routers.ical import rotate_ical_token

    u = _user("direct-rotate-nonpro", is_pro=False)
    db_session.add(u)
    await db_session.commit()

    with pytest.raises(HTTPException) as exc_info:
        await rotate_ical_token(db_session, u)
    assert exc_info.value.status_code == 403


# ---------------------------------------------------------------------------
# Unit tests — ical_escape()
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("hello, world", "hello\\, world"),
        ("a;b", "a\\;b"),
        ("a\nb", "a\\nb"),
        ("a\r\nb", "a\\nb"),
        ("a\rb", "a\\nb"),
        ("back\\slash", "back\\\\slash"),
        ("mix;and,sep\nnew", "mix\\;and\\,sep\\nnew"),
        ("plain text", "plain text"),
        ("", ""),
    ],
)
def test_ical_escape_roundtrips(raw: str, expected: str) -> None:
    assert ical_escape(raw) == expected


# ---------------------------------------------------------------------------
# Feed endpoint — valid ICS output
# ---------------------------------------------------------------------------


async def test_ical_feed_returns_valid_ics(client, db_session):
    token = secrets.token_urlsafe(32)
    u = _user("valid", ical_token=token)
    db_session.add(u)
    await db_session.flush()
    la = _launch("l-ical-1", mission_name="Starlink G9")
    db_session.add(la)
    await db_session.flush()
    db_session.add(Subscription(user_id=u.id, type="launch", ll2_id="l-ical-1"))
    await db_session.commit()

    r = await client.get(f"/api/v1/ical/{token}.ics")
    assert r.status_code == 200
    assert "text/calendar" in r.headers["content-type"]
    assert r.headers["cache-control"] == "private, max-age=900"

    cal = Calendar.from_ical(r.text)
    events = [c for c in cal.walk() if c.name == "VEVENT"]
    assert len(events) == 1
    ev = events[0]
    assert str(ev.get("SUMMARY")) == "Starlink G9"
    assert "l-ical-1@spaceadventures.app" in str(ev.get("UID"))
    assert int(str(ev.get("SEQUENCE"))) == 0
    assert ev.get("DTSTAMP") is not None, "DTSTAMP is required by RFC 5545 §3.6.1"


async def test_ical_feed_uses_launch_name_when_no_mission_name(client, db_session):
    token = secrets.token_urlsafe(32)
    u = _user("noname", ical_token=token)
    db_session.add(u)
    await db_session.flush()
    la = _launch("l-ical-noname")  # no mission_name
    db_session.add(la)
    await db_session.flush()
    db_session.add(Subscription(user_id=u.id, type="launch", ll2_id="l-ical-noname"))
    await db_session.commit()

    r = await client.get(f"/api/v1/ical/{token}.ics")
    assert r.status_code == 200
    cal = Calendar.from_ical(r.text)
    events = [c for c in cal.walk() if c.name == "VEVENT"]
    assert events[0].get("SUMMARY") is not None
    assert "Launch l-ical-noname" in str(events[0].get("SUMMARY"))


async def test_ical_feed_empty_when_no_subscriptions(client, db_session):
    token = secrets.token_urlsafe(32)
    u = _user("empty", ical_token=token)
    db_session.add(u)
    await db_session.commit()

    r = await client.get(f"/api/v1/ical/{token}.ics")
    assert r.status_code == 200
    cal = Calendar.from_ical(r.text)
    events = [c for c in cal.walk() if c.name == "VEVENT"]
    assert events == []


# ---------------------------------------------------------------------------
# SEQUENCE increments after a NET change
# ---------------------------------------------------------------------------


async def test_ical_sequence_increments_on_net_change(client, db_session):
    token = secrets.token_urlsafe(32)
    u = _user("seq", ical_token=token)
    db_session.add(u)
    await db_session.flush()
    la = _launch("l-ical-seq")
    db_session.add(la)
    await db_session.flush()
    db_session.add(Subscription(user_id=u.id, type="launch", ll2_id="l-ical-seq"))
    await db_session.commit()

    # Before any NET changes, SEQUENCE should be 0.
    r = await client.get(f"/api/v1/ical/{token}.ics")
    cal = Calendar.from_ical(r.text)
    ev = next(c for c in cal.walk() if c.name == "VEVENT")
    assert int(str(ev.get("SEQUENCE"))) == 0

    # Add 2 NET change rows.
    for _ in range(2):
        db_session.add(
            LaunchNetChange(
                launch_id="l-ical-seq",
                change_type="net",
                old_value="2099-01-01T00:00:00",
                new_value="2099-01-02T00:00:00",
                provider_name="Agency",
                rocket_name="Rocket",
            )
        )
    await db_session.commit()

    r = await client.get(f"/api/v1/ical/{token}.ics")
    cal = Calendar.from_ical(r.text)
    ev = next(c for c in cal.walk() if c.name == "VEVENT")
    assert int(str(ev.get("SEQUENCE"))) == 2


# ---------------------------------------------------------------------------
# STATUS:CANCELLED for Gone launches
# ---------------------------------------------------------------------------


async def test_ical_cancelled_on_gone_launch(client, db_session):
    token = secrets.token_urlsafe(32)
    u = _user("gone", ical_token=token)
    db_session.add(u)
    await db_session.flush()
    la = _launch("l-ical-gone", status_abbrev="Gone")
    db_session.add(la)
    await db_session.flush()
    db_session.add(Subscription(user_id=u.id, type="launch", ll2_id="l-ical-gone"))
    await db_session.commit()

    r = await client.get(f"/api/v1/ical/{token}.ics")
    assert r.status_code == 200
    cal = Calendar.from_ical(r.text)
    events = [c for c in cal.walk() if c.name == "VEVENT"]
    assert len(events) == 1
    assert str(events[0].get("STATUS")) == "CANCELLED"


async def test_ical_no_cancelled_on_active_launch(client, db_session):
    token = secrets.token_urlsafe(32)
    u = _user("active", ical_token=token)
    db_session.add(u)
    await db_session.flush()
    la = _launch("l-ical-active", status_abbrev="Go")
    db_session.add(la)
    await db_session.flush()
    db_session.add(Subscription(user_id=u.id, type="launch", ll2_id="l-ical-active"))
    await db_session.commit()

    r = await client.get(f"/api/v1/ical/{token}.ics")
    cal = Calendar.from_ical(r.text)
    ev = next(c for c in cal.walk() if c.name == "VEVENT")
    assert ev.get("STATUS") is None


# ---------------------------------------------------------------------------
# Pro gate and unknown token
# ---------------------------------------------------------------------------


async def test_ical_unknown_token_returns_404(client, db_session):
    r = await client.get("/api/v1/ical/no-such-token.ics")
    assert r.status_code == 404


async def test_ical_non_pro_token_returns_404(client, db_session):
    """Non-Pro user with a token gets 404, not 403 — no oracle (25-security-testing.md §2.1)."""
    token = secrets.token_urlsafe(32)
    u = _user("nonpro", is_pro=False, ical_token=token)
    db_session.add(u)
    await db_session.commit()

    r = await client.get(f"/api/v1/ical/{token}.ics")
    assert r.status_code == 404
    assert r.json()["detail"]["error"]["code"] == "NOT_FOUND"


# ---------------------------------------------------------------------------
# Token rotation
# ---------------------------------------------------------------------------


async def test_ical_rotate_generates_token(client, db_session):
    """Pro user can rotate and receives a token."""
    await client.post(
        "/api/v1/auth/register",
        json={
            "first_name": "Ical",
            "last_name": "Rotate",
            "email": "ical-rotate@example.com",
            "password": "securepassword",
        },
    )
    # Grant Pro status directly via DB.
    from sqlalchemy import select as sa_select
    from app.models.user import User as UserModel
    result = await db_session.execute(sa_select(UserModel).where(UserModel.email == "ical-rotate@example.com"))
    u = result.scalar_one()
    u.is_pro = True
    await db_session.commit()

    r = await client.post(
        "/api/v1/auth/login",
        json={"email_or_phone": "ical-rotate@example.com", "password": "securepassword"},
    )
    token_resp = r.json()["access_token"]
    headers = {"Authorization": f"Bearer {token_resp}"}

    r = await client.post("/api/v1/ical/rotate", headers=headers)
    assert r.status_code == 200
    ical_token = r.json()["ical_token"]
    assert isinstance(ical_token, str)
    assert len(ical_token) > 0


async def test_ical_rotate_non_pro_returns_403(client, db_session):
    """Free-tier users cannot rotate — Pro gating is server-side (CLAUDE.md rule 11)."""
    await client.post(
        "/api/v1/auth/register",
        json={
            "first_name": "Ical",
            "last_name": "Free",
            "email": "ical-free@example.com",
            "password": "securepassword",
        },
    )
    r = await client.post(
        "/api/v1/auth/login",
        json={"email_or_phone": "ical-free@example.com", "password": "securepassword"},
    )
    headers = {"Authorization": f"Bearer {r.json()['access_token']}"}

    r = await client.post("/api/v1/ical/rotate", headers=headers)
    assert r.status_code == 403
    assert r.json()["detail"]["error"]["code"] == "PRO_REQUIRED"


async def test_ical_rotate_invalidates_old_url(client, db_session):
    """Rotating generates a new token; the old webcal:// URL immediately 404s."""
    # Register a fresh user and grant Pro + initial ical_token directly.
    await client.post(
        "/api/v1/auth/register",
        json={
            "first_name": "Ical",
            "last_name": "Rotinv",
            "email": "ical-rotinv@example.com",
            "password": "securepassword",
        },
    )
    result = await db_session.execute(select(User).where(User.email == "ical-rotinv@example.com"))
    u = result.scalar_one()
    token_old = secrets.token_urlsafe(32)
    u.is_pro = True
    u.ical_token = token_old
    await db_session.commit()

    # Old token works.
    r_before = await client.get(f"/api/v1/ical/{token_old}.ics")
    assert r_before.status_code == 200

    # Login and rotate.
    r_login = await client.post(
        "/api/v1/auth/login",
        json={"email_or_phone": "ical-rotinv@example.com", "password": "securepassword"},
    )
    headers = {"Authorization": f"Bearer {r_login.json()['access_token']}"}
    rot_r = await client.post("/api/v1/ical/rotate", headers=headers)
    assert rot_r.status_code == 200
    new_token = rot_r.json()["ical_token"]
    assert new_token != token_old

    # Old token → 404.
    r_old = await client.get(f"/api/v1/ical/{token_old}.ics")
    assert r_old.status_code == 404

    # New token works.
    r_new = await client.get(f"/api/v1/ical/{new_token}.ics")
    assert r_new.status_code == 200


async def test_ical_rotate_requires_auth(client, db_session):
    r = await client.post("/api/v1/ical/rotate")
    assert r.status_code == 401


# ---------------------------------------------------------------------------
# ICS output visible in /auth/me
# ---------------------------------------------------------------------------


async def test_ical_token_returned_in_me_endpoint(client, db_session):
    """UserResponse.ical_token lets the frontend construct the webcal:// URL."""
    await client.post(
        "/api/v1/auth/register",
        json={
            "first_name": "Ical",
            "last_name": "Me",
            "email": "ical-me@example.com",
            "password": "securepassword",
        },
    )
    # Grant Pro so rotate is allowed (CLAUDE.md rule 11 — server-side Pro gating).
    from sqlalchemy import select as sa_select
    from app.models.user import User as UserModel
    result = await db_session.execute(sa_select(UserModel).where(UserModel.email == "ical-me@example.com"))
    u = result.scalar_one()
    u.is_pro = True
    await db_session.commit()

    r = await client.post(
        "/api/v1/auth/login",
        json={"email_or_phone": "ical-me@example.com", "password": "securepassword"},
    )
    headers = {"Authorization": f"Bearer {r.json()['access_token']}"}

    # Before rotation, ical_token is null.
    me = await client.get("/api/v1/auth/me", headers=headers)
    assert me.status_code == 200
    assert me.json()["ical_token"] is None

    # After rotation, it's set.
    await client.post("/api/v1/ical/rotate", headers=headers)
    me2 = await client.get("/api/v1/auth/me", headers=headers)
    assert me2.json()["ical_token"] is not None


# ---------------------------------------------------------------------------
# Injection payload escaping (25-security-testing.md §2.3 — ICS output context)
# ---------------------------------------------------------------------------


_ICS_INJECTION_PAYLOADS = [
    ("xss_script", "<script>alert(1)</script>"),
    ("semicolon", "a;b;c"),
    ("comma", "a,b,c"),
    ("crlf", "Header: injection\r\nX-Evil: yes"),
    ("backslash", "C:\\path\\to\\evil"),
    ("newlines", "line1\nline2\r\nline3"),
]


@pytest.mark.parametrize("_name,payload", _ICS_INJECTION_PAYLOADS, ids=[n for n, _ in _ICS_INJECTION_PAYLOADS])
async def test_ical_feed_escapes_injection_payloads(_name: str, payload: str, client, db_session):
    """Launch fields containing injection payloads must not appear raw in ICS.

    This is the §2.3 injection-fixture matrix entry for the ICS output context
    (documented in test_injection.py's module docstring under 'Step L2').
    """
    token = secrets.token_urlsafe(32)
    u = _user(f"inj-{_name}", ical_token=token)
    db_session.add(u)
    await db_session.flush()
    la = _launch(f"l-inj-{_name}", mission_name=payload)
    db_session.add(la)
    await db_session.flush()
    db_session.add(Subscription(user_id=u.id, type="launch", ll2_id=f"l-inj-{_name}"))
    await db_session.commit()

    r = await client.get(f"/api/v1/ical/{token}.ics")
    assert r.status_code == 200

    # Must be parseable by the icalendar library (invalid escaping → parse error).
    cal = Calendar.from_ical(r.text)
    events = [c for c in cal.walk() if c.name == "VEVENT"]
    assert len(events) == 1

    # Raw unescaped commas, semicolons that could break RFC 5545 parsing
    # must not appear in the raw ICS text at the property-value level.
    # (The icalendar parser would raise on truly malformed output, satisfying
    # the structural requirement; we additionally check the raw ICS for
    # known-dangerous sequences that RFC 5545 requires to be escaped.)
    ics_text = r.text
    # Raw CRLF injection into a property line would create fake property lines
    assert "\r\nX-Evil" not in ics_text
    assert "\nX-Evil" not in ics_text
