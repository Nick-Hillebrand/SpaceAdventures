"""Injection & untrusted-data test suite (Architecture/25-security-testing.md §2.3).

Parametrized fixture payloads verify that all fields flowing from LL2 (and
other upstream sources as they are added) into storage or output channels
are correctly escaped, stripped, or truncated before persistence.

Stage-1 scope (Step P4): LL2 → launch_net_changes (provider_name,
rocket_name, pad_name, old_value, new_value). Notification-output paths
(email, SMS) are covered by test_notifications.py; this file targets the
slip-history storage path specifically, and the underlying sanitise()
helper.

Step B1.2 (Web Push): `PushSubscribeRequest.endpoint`/`keys.p256dh`/
`keys.auth` are browser-supplied, but they are *not* in scope for this
fixture matrix — they are opaque values handed unmodified to pywebpush and
are never rendered into HTML/ICS/SEO-meta/JSON-LD/SMS/social output (the
§2.3 injection concern), nor interpolated into SQL (ORM-only, values are
bound parameters). `endpoint` is instead an SSRF concern (§2.5 — the worker
later makes an outbound HTTP request to whatever URL is stored), which is
covered separately: see `test_push.py::test_subscribe_rejects_unsafe_endpoint`
and `_validate_push_endpoint()` in `app/schemas/push.py`.

Step B3 (JPL Horizons, `22-ephemeris-and-mission-replay.md`): the `result`
CSV text block returned by Horizons is untrusted upstream input, but its
fields (`JDTDB`, X/Y/Z vector components) are constrained to be numeric —
`parse_vectors_csv()` in `app/services/horizons_client.py` parses every
field with `float()` and raises `HorizonsError("HORIZONS_PARSE_ERROR", ...)`
on anything that fails to convert, including injection-shaped strings (see
`test_horizons_client.py::test_parse_vectors_csv_non_numeric_field_raises_parse_error`,
parametrized over `<script>`/SQLi/non-numeric payloads). There is no
string-typed Horizons field that ever reaches storage or an output context
(HTML/ICS/SEO-meta/JSON-LD/SMS/social) — like Web Push's opaque keys, this
source is out of scope for the fixture matrix below, and coverage lives in
`test_horizons_client.py` instead.
"""
from __future__ import annotations

import json

import pytest

from app.services.notification_service import sanitise

# ---------------------------------------------------------------------------
# Fixture payloads (25-security-testing.md §2.3)
# ---------------------------------------------------------------------------

_INJECTION_PAYLOADS: list[tuple[str, str]] = [
    ("xss_script", "<script>alert(1)</script>"),
    ("ssti_braces", "\"'>{{7*7}}"),
    ("crlf_header", "Header: injection\r\nX-Evil: yes"),
    ("null_byte", "evil\x00string"),
    ("overlong", "A" * 10_001),
    ("rtl_override", "safe‮evil"),
    ("control_chars", "foo\x01\x1f\x7fbar"),
    ("null_with_cr", "abc\r\ndef"),
]

_PAYLOAD_IDS = [name for name, _ in _INJECTION_PAYLOADS]


@pytest.mark.parametrize("_name,payload", _INJECTION_PAYLOADS, ids=_PAYLOAD_IDS)
def test_sanitise_strips_control_characters(_name: str, payload: str) -> None:
    """sanitise() must remove CR, LF, NUL, and C0/DEL control characters."""
    result = sanitise(payload)
    assert "\r" not in result
    assert "\n" not in result
    assert "\x00" not in result
    for cp in range(0x01, 0x20):
        assert chr(cp) not in result, f"Control char U+{cp:04X} survived sanitise()"
    assert "\x7f" not in result


@pytest.mark.parametrize("_name,payload", _INJECTION_PAYLOADS, ids=_PAYLOAD_IDS)
def test_sanitise_result_is_string(_name: str, payload: str) -> None:
    """sanitise() always returns a str (never raises, never returns None)."""
    result = sanitise(payload)
    assert isinstance(result, str)


# ---------------------------------------------------------------------------
# Slip-history storage path: LL2 → launch_net_changes
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("_name,payload", _INJECTION_PAYLOADS, ids=_PAYLOAD_IDS)
async def test_slip_history_sanitises_provider_name(_name: str, payload: str, db_session) -> None:
    """provider_name from LL2 is sanitised before insertion into launch_net_changes."""
    from app.models.launch_net_changes import LaunchNetChange
    from app.models.launches import Launch
    from app.services.launches_service import _record_change, sync_launches
    from tests.test_launches_service_unit import FakeLL2Client, _raw

    # Seed a launch row so the FK is satisfied
    await sync_launches(db_session, FakeLL2Client([_raw()]))

    _record_change(
        db_session,
        launch_id="l-1",
        change_type="net",
        provider_name=payload,
        rocket_name="Falcon 9",
        pad_name=None,
        old_value="2099-01-01T00:00:00+00:00",
        new_value="2099-01-02T00:00:00+00:00",
    )
    await db_session.commit()

    from sqlalchemy import select
    result = await db_session.execute(select(LaunchNetChange))
    rows = list(result.scalars().all())
    net_rows = [r for r in rows if r.change_type == "net"]
    assert net_rows, "Expected at least one 'net' row"
    stored = net_rows[-1].provider_name
    assert "\r" not in stored
    assert "\n" not in stored
    assert "\x00" not in stored


@pytest.mark.parametrize("_name,payload", _INJECTION_PAYLOADS, ids=_PAYLOAD_IDS)
async def test_slip_history_sanitises_rocket_name(_name: str, payload: str, db_session) -> None:
    """rocket_name from LL2 is sanitised before insertion into launch_net_changes."""
    from app.models.launch_net_changes import LaunchNetChange
    from app.services.launches_service import _record_change, sync_launches
    from tests.test_launches_service_unit import FakeLL2Client, _raw

    await sync_launches(db_session, FakeLL2Client([_raw()]))
    _record_change(
        db_session,
        launch_id="l-1",
        change_type="status",
        provider_name="SpaceX",
        rocket_name=payload,
        pad_name=None,
        old_value="Go",
        new_value="Hold",
    )
    await db_session.commit()

    from sqlalchemy import select
    result = await db_session.execute(select(LaunchNetChange))
    rows = [r for r in result.scalars().all() if r.change_type == "status"]
    assert rows
    stored = rows[-1].rocket_name
    assert "\r" not in stored
    assert "\n" not in stored
    assert "\x00" not in stored


# ---------------------------------------------------------------------------
# SEO meta-injection rendering path: launches table (raw LL2 fields, never
# passed through sanitise() — only the launch_net_changes table is) → HTML
# meta/OG/Twitter tags + schema.org JSON-LD (Step B2,
# 23-seo-widgets-and-growth.md). This is the first HTML-rendering consumer of
# Launch row fields, so the relevant control is html.escape() for the meta
# tags and the "<" → "<" neutralisation in `_json_ld_safe()` for the
# JSON-LD `<script>` block — not sanitise()'s control-character stripping.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("_name,payload", _INJECTION_PAYLOADS, ids=_PAYLOAD_IDS)
async def test_seo_meta_escapes_untrusted_mission_name(_name: str, payload: str, db_session) -> None:
    """A mission_name straight from LL2 can never survive unescaped into the
    rendered <title>/meta/OG/Twitter tags or break out of the JSON-LD
    <script> block."""
    from app.config import Settings
    from app.routers.seo import _build_seo_head
    from app.services.launches_service import get_launch_by_id, sync_launches
    from tests.test_launches_service_unit import FakeLL2Client, _raw

    await sync_launches(
        db_session,
        FakeLL2Client(
            [_raw(ll2_id="l-inj", mission={"name": payload, "description": "Sats.", "type": "Comms"})]
        ),
    )
    launch = await get_launch_by_id(db_session, "l-inj")
    assert launch is not None

    settings = Settings(require_secrets=False, frontend_origin="https://example.test")  # type: ignore[call-arg]
    title_tag, rest = _build_seo_head(launch, "en", settings)

    # The meta/title/OG/Twitter portion (html.escape()) and the JSON-LD
    # <script> block (json.dumps() + `_json_ld_safe()`) have different
    # escaping rules, so they must be checked separately: a `"` inside a
    # JSON string is legitimately preserved (backslash-escaped) by
    # json.dumps() — that is correct, safe JSON, not a leak — whereas the
    # same raw `"` surviving into an HTML attribute value would be a real
    # break-out.
    script_open = '<script type="application/ld+json">'
    script_start = rest.index(script_open)
    json_ld_start = script_start + len(script_open)
    json_ld_end = rest.index("</script>", json_ld_start)
    json_ld_body = rest[json_ld_start:json_ld_end]
    html_part = title_tag + "\n" + rest[:script_start]

    if any(c in payload for c in "<>&\"'"):
        assert payload not in html_part, (
            f"raw, unescaped mission_name payload ({_name}) leaked into SEO "
            "meta/OG/Twitter tag output"
        )

    # The JSON-LD block itself must remain syntactically valid JSON (proving
    # the payload was safely embedded as string data) and must never contain
    # a literal "</script" that could break out of the surrounding
    # <script type="application/ld+json"> tag, regardless of what LL2 sent.
    json.loads(json_ld_body)
    assert "</script" not in json_ld_body.lower()


@pytest.mark.parametrize("_name,payload", _INJECTION_PAYLOADS, ids=_PAYLOAD_IDS)
async def test_seo_meta_escapes_untrusted_agency_rocket_pad_names(
    _name: str, payload: str, db_session
) -> None:
    """agency_name/rocket_name/pad_name are the same untrusted-LL2-field
    shape as mission_name, but reach SEO output through two different code
    paths: pad_name always lands in the JSON-LD `location.name`, while
    agency_name/rocket_name only appear in the html.escape()'d meta
    description when there is no mission_description to prefer (the
    `_build_seo_head` fallback string)."""
    from app.config import Settings
    from app.routers.seo import _build_seo_head
    from app.services.launches_service import get_launch_by_id, sync_launches
    from tests.test_launches_service_unit import FakeLL2Client, _raw

    await sync_launches(
        db_session,
        FakeLL2Client(
            [
                _raw(
                    ll2_id="l-inj-2",
                    launch_service_provider={"name": payload, "type": "Commercial"},
                    rocket={"configuration": {"name": payload, "family": "Falcon"}},
                    pad={"name": payload, "location": {"name": "Cape Canaveral"}},
                    mission={"name": "Starlink", "description": "", "type": "Comms"},
                )
            ]
        ),
    )
    launch = await get_launch_by_id(db_session, "l-inj-2")
    assert launch is not None

    settings = Settings(require_secrets=False, frontend_origin="https://example.test")  # type: ignore[call-arg]
    title_tag, rest = _build_seo_head(launch, "en", settings)

    script_open = '<script type="application/ld+json">'
    script_start = rest.index(script_open)
    json_ld_start = script_start + len(script_open)
    json_ld_end = rest.index("</script>", json_ld_start)
    json_ld_body = rest[json_ld_start:json_ld_end]
    html_part = title_tag + "\n" + rest[:script_start]

    if any(c in payload for c in "<>&\"'"):
        assert payload not in html_part, (
            f"raw, unescaped agency/rocket/pad payload ({_name}) leaked into the "
            "SEO description fallback"
        )

    json.loads(json_ld_body)
    assert "</script" not in json_ld_body.lower()


# ---------------------------------------------------------------------------
# SQL injection guard: ORM-only check (25-security-testing.md §2.3)
# ---------------------------------------------------------------------------


def test_no_raw_sql_interpolation_in_launches_service() -> None:
    """Grep guard: launches_service.py must not use string-interpolated text()."""
    import ast
    import pathlib

    src = pathlib.Path(__file__).parents[2] / "app" / "services" / "launches_service.py"
    tree = ast.parse(src.read_text())

    # Look for calls to text() or execute() with a non-literal first argument
    violations: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        # Detect sqlalchemy text() calls
        is_text_call = (isinstance(func, ast.Name) and func.id == "text") or (
            isinstance(func, ast.Attribute) and func.attr == "text"
        )
        if is_text_call and node.args:
            arg = node.args[0]
            if not isinstance(arg, ast.Constant):
                violations.append(f"line {node.lineno}: text() with non-literal arg")

    assert not violations, "Potential SQL injection via text(): " + "; ".join(violations)
