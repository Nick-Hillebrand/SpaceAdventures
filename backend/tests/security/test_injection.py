"""Injection & untrusted-data test suite (Architecture/25-security-testing.md §2.3).

Parametrized fixture payloads verify that all fields flowing from LL2 (and
other upstream sources as they are added) into storage or output channels
are correctly escaped, stripped, or truncated before persistence.

Stage-1 scope (Step P4): LL2 → launch_net_changes (provider_name,
rocket_name, pad_name, old_value, new_value). Notification-output paths
(email, SMS) are covered by test_notifications.py; this file targets the
slip-history storage path specifically, and the underlying sanitise()
helper.
"""
from __future__ import annotations

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
