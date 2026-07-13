"""Space Weather caching service (DONKI).

Five event types — FLR, GST, RBE, SEP, CME — each fetched from a separate
DONKI endpoint. All share the same permanent-cache logic:

- Historical range with cached rows → return immediately (cached=True).
- Range includes today (UTC) → always re-fetch and upsert.
- Upstream failure but cached rows exist → stale=True.
- No cache and upstream fails → propagate NasaClientError.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import SpaceWeatherEvent
from app.services.nasa_client import NasaClient, NasaClientError

EventType = Literal["FLR", "GST", "RBE", "SEP", "CME"]

_DONKI_PATHS: dict[EventType, str] = {
    "FLR": "/DONKI/FLR",
    "GST": "/DONKI/GST",
    "RBE": "/DONKI/RBE",
    "SEP": "/DONKI/SEP",
    "CME": "/DONKI/CME",
}

_START_DATE_FIELDS: dict[EventType, list[str]] = {
    "FLR": ["beginTime", "peakTime", "startTime"],
    "GST": ["startTime"],
    "RBE": ["eventTime"],
    "SEP": ["eventTime"],
    "CME": ["startTime", "activityID"],
}


def _today_utc() -> date:
    return datetime.now(timezone.utc).date()


def _validate_range(start: str, end: str) -> tuple[date, date]:
    s = date.fromisoformat(start)
    e = date.fromisoformat(end)
    if e < s:
        raise ValueError("end must be on or after start")
    return s, e


def _extract_id(obj: dict, event_type: EventType) -> str | None:
    """Return the best available unique identifier from an event object."""
    # Most DONKI events have a *ID field
    for key in (f"{event_type.lower()}ID", "activityID", "gstID", "flrID", "sepID", "rbeID"):
        val = obj.get(key)
        if val:
            return str(val)
    return None


def _extract_start_date(obj: dict, event_type: EventType, fallback: str) -> str:
    for field in _START_DATE_FIELDS.get(event_type, []):
        val = obj.get(field)
        if val:
            # DONKI timestamps look like "2020-01-01T12:00Z" — take date part
            return str(val)[:10]
    return fallback


def _row_from_event(obj: dict, event_type: EventType, feed_date: str) -> SpaceWeatherEvent | None:
    event_id = _extract_id(obj, event_type)
    if not event_id:
        return None
    start_date = _extract_start_date(obj, event_type, feed_date)
    return SpaceWeatherEvent(
        id=f"{event_type}:{event_id}",
        event_type=event_type,
        start_date=start_date,
        raw_json=obj,
        fetched_at=datetime.now(timezone.utc),
    )


async def _upsert_events(
    session: AsyncSession, events: list[dict], event_type: EventType, feed_date: str
) -> None:
    for obj in events:
        row = _row_from_event(obj, event_type, feed_date)
        if row is None:
            continue
        existing = await session.get(SpaceWeatherEvent, row.id)
        if existing is None:
            session.add(row)
        else:
            existing.start_date = row.start_date
            existing.raw_json = row.raw_json
            existing.fetched_at = row.fetched_at
    await session.commit()


async def _query_range(
    session: AsyncSession, event_type: EventType, start: date, end: date
) -> list[SpaceWeatherEvent]:
    result = await session.execute(
        select(SpaceWeatherEvent)
        .where(SpaceWeatherEvent.event_type == event_type)
        .where(SpaceWeatherEvent.start_date >= start.isoformat())
        .where(SpaceWeatherEvent.start_date <= end.isoformat())
        .order_by(SpaceWeatherEvent.start_date)
    )
    return list(result.scalars().all())


class SpaceWeatherResult:
    def __init__(
        self,
        rows: list[SpaceWeatherEvent],
        cached: bool,
        stale: bool,
        is_today: bool,
        fetched_at: datetime,
    ) -> None:
        self.rows = rows
        self.cached = cached
        self.stale = stale
        self.is_today = is_today
        self.fetched_at = fetched_at


def _latest_fetched_at(rows: list[SpaceWeatherEvent]) -> datetime:
    if not rows:
        return datetime.now(timezone.utc)
    return max(r.fetched_at for r in rows)


async def fetch_events(
    session: AsyncSession,
    client: NasaClient,
    event_type: EventType,
    start: str,
    end: str,
) -> SpaceWeatherResult:
    """Return DONKI events for ``event_type`` in ``[start, end]``."""
    s, e = _validate_range(start, end)
    is_today = e >= _today_utc()

    existing = await _query_range(session, event_type, s, e)

    if existing and not is_today:
        return SpaceWeatherResult(
            rows=existing,
            cached=True,
            stale=False,
            is_today=False,
            fetched_at=_latest_fetched_at(existing),
        )

    path = _DONKI_PATHS[event_type]
    try:
        payload = await client.get(
            path,
            params={"startDate": s.isoformat(), "endDate": e.isoformat()},
        )
    except NasaClientError:
        if existing:
            return SpaceWeatherResult(
                rows=existing,
                cached=True,
                stale=True,
                is_today=is_today,
                fetched_at=_latest_fetched_at(existing),
            )
        raise

    # DONKI returns a list (or null when no events)
    events: list[dict] = payload if isinstance(payload, list) else []
    await _upsert_events(session, events, event_type, s.isoformat())
    rows = await _query_range(session, event_type, s, e)
    return SpaceWeatherResult(
        rows=rows,
        cached=False,
        stale=False,
        is_today=is_today,
        fetched_at=_latest_fetched_at(rows),
    )
