"""NEO (Near-Earth Object) caching service.

Implements the permanent cache pattern per Architecture/03-caching-strategy.md
for the NASA NeoWs feed endpoint (`/neo/rest/v1/feed`).

Caching semantics:

- Range excluding today (UTC) with any cached rows → return cached rows,
  no upstream call.
- Range including today OR no cached rows → call NASA, upsert per-NEO rows.
- Upstream failure but cached rows exist → return cached with ``stale=True``.
- No cache and upstream fails → propagate ``NasaClientError``.

The NASA feed enforces a maximum 7-day window per request; that same
constraint is validated here before making a request.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Neo
from app.services.nasa_client import NasaClient, NasaClientError
from app.services.url_utils import sanitise_url

NEO_PATH = "/neo/rest/v1/feed"
MAX_RANGE_DAYS = 7


def _today_utc() -> date:
    return datetime.now(timezone.utc).date()


def _range_includes_today(end: date) -> bool:
    return end >= _today_utc()


def _validate_range(start: str, end: str) -> tuple[date, date]:
    s = date.fromisoformat(start)
    e = date.fromisoformat(end)
    if e < s:
        raise ValueError("end must be on or after start")
    if (e - s).days + 1 > MAX_RANGE_DAYS:
        raise ValueError("range must be at most 7 days")
    return s, e


def _coerce_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _neo_from_object(obj: dict, feed_date: str) -> Neo:
    approaches = obj.get("close_approach_data") or []
    approach: dict = approaches[0] if approaches else {}

    diameter_km = (obj.get("estimated_diameter") or {}).get("kilometers") or {}
    velocity_map = approach.get("relative_velocity") or {}
    miss_map = approach.get("miss_distance") or {}

    return Neo(
        id=str(obj.get("id")),
        name=str(obj.get("name") or ""),
        close_approach_date=str(approach.get("close_approach_date") or feed_date),
        absolute_magnitude_h=_coerce_float(obj.get("absolute_magnitude_h")),
        estimated_diameter_min_km=_coerce_float(diameter_km.get("estimated_diameter_min")),
        estimated_diameter_max_km=_coerce_float(diameter_km.get("estimated_diameter_max")),
        is_potentially_hazardous=bool(obj.get("is_potentially_hazardous_asteroid", False)),
        relative_velocity_kph=_coerce_float(velocity_map.get("kilometers_per_hour")),
        miss_distance_km=_coerce_float(miss_map.get("kilometers")),
        orbiting_body=approach.get("orbiting_body"),
        nasa_jpl_url=sanitise_url(obj.get("nasa_jpl_url")),
        fetched_at=datetime.now(timezone.utc).replace(tzinfo=None),
    )


async def _upsert_payload(session: AsyncSession, payload: dict) -> None:
    near_objects = payload.get("near_earth_objects") or {}
    for feed_date, entries in near_objects.items():
        for obj in entries or []:
            fresh = _neo_from_object(obj, feed_date)
            existing = await session.get(Neo, fresh.id)
            if existing is None:
                session.add(fresh)
            else:
                existing.name = fresh.name
                existing.close_approach_date = fresh.close_approach_date
                existing.absolute_magnitude_h = fresh.absolute_magnitude_h
                existing.estimated_diameter_min_km = fresh.estimated_diameter_min_km
                existing.estimated_diameter_max_km = fresh.estimated_diameter_max_km
                existing.is_potentially_hazardous = fresh.is_potentially_hazardous
                existing.relative_velocity_kph = fresh.relative_velocity_kph
                existing.miss_distance_km = fresh.miss_distance_km
                existing.orbiting_body = fresh.orbiting_body
                existing.nasa_jpl_url = fresh.nasa_jpl_url
                existing.fetched_at = fresh.fetched_at
    await session.commit()


async def _query_range(session: AsyncSession, start: date, end: date) -> list[Neo]:
    result = await session.execute(
        select(Neo)
        .where(Neo.close_approach_date >= start.isoformat())
        .where(Neo.close_approach_date <= end.isoformat())
        .order_by(Neo.close_approach_date, Neo.name)
    )
    return list(result.scalars().all())


class NeoResult:
    def __init__(
        self,
        rows: list[Neo],
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


def _latest_fetched_at(rows: list[Neo]) -> datetime:
    if not rows:
        return datetime.now(timezone.utc).replace(tzinfo=None)
    return max(row.fetched_at for row in rows)


async def fetch_neo_feed(
    session: AsyncSession, client: NasaClient, start: str, end: str
) -> NeoResult:
    """Return NEOs for ``[start, end]`` (YYYY-MM-DD) applying caching policy."""
    s, e = _validate_range(start, end)
    is_today = _range_includes_today(e)

    existing = await _query_range(session, s, e)

    if existing and not is_today:
        return NeoResult(
            rows=existing,
            cached=True,
            stale=False,
            is_today=False,
            fetched_at=_latest_fetched_at(existing),
        )

    try:
        payload = await client.get(
            NEO_PATH,
            params={"start_date": s.isoformat(), "end_date": e.isoformat()},
        )
    except NasaClientError:
        if existing:
            return NeoResult(
                rows=existing,
                cached=True,
                stale=True,
                is_today=is_today,
                fetched_at=_latest_fetched_at(existing),
            )
        raise

    await _upsert_payload(session, payload)
    rows = await _query_range(session, s, e)
    return NeoResult(
        rows=rows,
        cached=False,
        stale=False,
        is_today=is_today,
        fetched_at=_latest_fetched_at(rows),
    )
