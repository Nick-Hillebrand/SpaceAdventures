"""APOD caching service.

Implements the permanent cache pattern per Architecture/03-caching-strategy.md:

- Historical date → cache hit returns without upstream call.
- Today (UTC) → always re-fetch and upsert.
- Any upstream error but cached row exists → return cached with ``stale=True``.
- No cached row and upstream error → propagate ``NasaClientError``.
"""

from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Apod
from app.services.nasa_client import NasaClient, NasaClientError

APOD_PATH = "/planetary/apod"


def _today_utc() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def _is_today(target_date: str) -> bool:
    return target_date == _today_utc()


def _apod_from_payload(payload: dict, target_date: str) -> Apod:
    return Apod(
        date=payload.get("date", target_date),
        title=payload.get("title", ""),
        explanation=payload.get("explanation", ""),
        url=payload.get("url", ""),
        hdurl=payload.get("hdurl"),
        media_type=payload.get("media_type", "image"),
        copyright=payload.get("copyright"),
        thumbnail_url=payload.get("thumbnail_url"),
        fetched_at=datetime.now(timezone.utc).replace(tzinfo=None),
    )


async def _upsert(session: AsyncSession, target_date: str, payload: dict) -> Apod:
    existing = await session.get(Apod, target_date)
    fresh = _apod_from_payload(payload, target_date)
    if existing is None:
        session.add(fresh)
        row = fresh
    else:
        existing.title = fresh.title
        existing.explanation = fresh.explanation
        existing.url = fresh.url
        existing.hdurl = fresh.hdurl
        existing.media_type = fresh.media_type
        existing.copyright = fresh.copyright
        existing.thumbnail_url = fresh.thumbnail_url
        existing.fetched_at = fresh.fetched_at
        row = existing
    await session.commit()
    await session.refresh(row)
    return row


class ApodResult:
    def __init__(self, row: Apod, cached: bool, stale: bool, is_today: bool) -> None:
        self.row = row
        self.cached = cached
        self.stale = stale
        self.is_today = is_today


def _validate_date(target_date: str) -> date:
    return date.fromisoformat(target_date)


async def fetch_apod(
    session: AsyncSession, client: NasaClient, target_date: str
) -> ApodResult:
    """Return APOD for ``target_date`` (YYYY-MM-DD) applying the caching policy."""
    parsed = _validate_date(target_date)
    is_today = _is_today(parsed.isoformat())

    existing = await session.get(Apod, parsed.isoformat())

    if existing is not None and not is_today:
        return ApodResult(existing, cached=True, stale=False, is_today=False)

    try:
        payload = await client.get(APOD_PATH, params={"date": parsed.isoformat()})
    except NasaClientError:
        if existing is not None:
            return ApodResult(existing, cached=True, stale=True, is_today=is_today)
        raise

    row = await _upsert(session, parsed.isoformat(), payload)
    return ApodResult(row, cached=False, stale=False, is_today=is_today)
