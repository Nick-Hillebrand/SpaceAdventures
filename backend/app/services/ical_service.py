"""iCal feed generation (Architecture/19-notification-channels-v2.md L2).

Builds a VCALENDAR of a user's subscribed launches, one VEVENT per launch.
SEQUENCE increments with every NET change so calendar clients can update
existing events in-place.

LL2 data is untrusted upstream input: every string field rendered into the
ICS output is passed through sanitise() then ical_escape() — sanitise()
strips control characters, ical_escape() applies RFC 5545 §3.3.11 TEXT
escaping (commas, semicolons, backslashes, newlines).
"""
from __future__ import annotations

import secrets
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.launch_net_changes import LaunchNetChange
from app.models.launches import Launch
from app.models.subscription import Subscription
from app.models.user import User
from app.services.notification_service import ical_escape, sanitise

_DOMAIN = "spaceadventures.app"
_PRODID = "-//Space Adventures//Space Adventures Calendar//EN"
_CRLF = "\r\n"
_LINE_MAX = 75  # RFC 5545 §3.1 folding limit in octets


def _fold(line: str) -> str:
    """Fold a single iCal content line at 75 octets per RFC 5545 §3.1.

    Folding is per-octet (UTF-8), not per character. For ASCII-heavy content
    this is effectively per-character; we use a conservative encode-then-
    split approach to handle multi-byte characters correctly.
    """
    encoded = line.encode("utf-8")
    if len(encoded) <= _LINE_MAX:
        return line
    chunks: list[bytes] = []
    pos = 0
    first = True
    while pos < len(encoded):
        limit = _LINE_MAX if first else _LINE_MAX - 1  # continuation lines lose 1 for the leading space
        chunk = encoded[pos : pos + limit]
        # Back off until we have a valid UTF-8 boundary.
        while len(chunk) > 0:
            try:
                chunk.decode("utf-8")
                break
            except UnicodeDecodeError:
                chunk = chunk[:-1]
        if not chunk:
            # Should never happen with well-formed UTF-8; advance one byte and continue.
            chunk = encoded[pos : pos + 1]
        chunks.append(chunk)
        pos += len(chunk)
        first = False
    return _CRLF.join(
        (b if i == 0 else b" " + b).decode("utf-8")
        for i, b in enumerate(chunks)
    )


def _fmt_dt(dt) -> str:
    """Format a datetime as an RFC 5545 UTC timestamp: YYYYMMDDTHHMMSSZ."""
    utc = dt.astimezone(timezone.utc)
    return utc.strftime("%Y%m%dT%H%M%SZ")


def _vevent_lines(
    launch: Launch,
    net_change_count: int,
) -> list[str]:
    summary_raw = launch.mission_name or launch.name
    summary = ical_escape(sanitise(summary_raw))

    status_part = ical_escape(sanitise(launch.status_name))
    urls = launch.livestream_urls or []
    if urls:
        first_url = urls[0].get("url", "") if isinstance(urls[0], dict) else str(urls[0])
        desc = f"Status: {status_part}\\nURL: {ical_escape(sanitise(first_url))}"
    else:
        desc = f"Status: {status_part}"

    now_utc = _fmt_dt(datetime.now(timezone.utc))
    lines = [
        "BEGIN:VEVENT",
        f"UID:{launch.ll2_id}@{_DOMAIN}",
        f"DTSTAMP:{now_utc}",
        f"DTSTART:{_fmt_dt(launch.net)}",
        f"SUMMARY:{summary}",
        f"DESCRIPTION:{desc}",
        f"SEQUENCE:{net_change_count}",
    ]
    if launch.status_abbrev == "Gone":
        lines.append("STATUS:CANCELLED")
    lines.append("END:VEVENT")
    return lines


def _build_ics(events: list[tuple[Launch, int]]) -> str:
    all_lines: list[str] = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        f"PRODID:{_PRODID}",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "X-WR-CALNAME:Space Adventures Launches",
    ]
    for launch, net_changes in events:
        all_lines.extend(_vevent_lines(launch, net_changes))
    all_lines.append("END:VCALENDAR")
    return _CRLF.join(_fold(line) for line in all_lines) + _CRLF


async def get_user_by_ical_token(session: AsyncSession, token: str) -> User | None:
    result = await session.execute(select(User).where(User.ical_token == token))
    return result.scalar_one_or_none()


async def build_calendar(session: AsyncSession, user: User) -> str:
    """Build the VCALENDAR ICS string for a user's launch subscriptions.

    Two queries total (row-count-independent):
    1. Load subscribed launches joined with NET-change counts in one query.
    """
    net_count_sub = (
        select(func.count())
        .select_from(LaunchNetChange)
        .where(
            LaunchNetChange.launch_id == Launch.ll2_id,
            LaunchNetChange.change_type == "net",
        )
        .correlate(Launch)
        .scalar_subquery()
    )
    stmt = (
        select(Launch, net_count_sub.label("net_changes"))
        .join(Subscription, Subscription.ll2_id == Launch.ll2_id)
        .where(
            Subscription.user_id == user.id,
            Subscription.type == "launch",
        )
        .order_by(Launch.net)
    )
    rows = (await session.execute(stmt)).all()
    events = [(row.Launch, row.net_changes or 0) for row in rows]
    return _build_ics(events)


async def rotate_token(session: AsyncSession, user: User) -> str:
    """Generate (or regenerate) the user's iCal token.

    Returns the new raw token. The old URL immediately becomes a 404.
    """
    token = secrets.token_urlsafe(32)
    user.ical_token = token
    await session.commit()
    return token
