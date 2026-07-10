"""APOD caching service.

Implements the permanent cache pattern per Architecture/03-caching-strategy.md:

- Historical date → cache hit returns without upstream call.
- Today (UTC) → always re-fetch and upsert.
- Any upstream error but cached row exists → return cached with ``stale=True``.
- No cached row and upstream error → propagate ``NasaClientError``.

Translations are filled eagerly when a ``translator`` callable is supplied:
    translator: async (fields: dict[str, str]) -> dict[str, dict[str, str]]
Tests omit the translator (default None) so no network translation is attempted.
"""

from __future__ import annotations

import json
import logging
from datetime import date, datetime, timezone
from typing import Any, Awaitable, Callable

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Apod
from app.services.nasa_client import NasaClient, NasaClientError
from app.services.url_utils import sanitise_url

logger = logging.getLogger(__name__)

APOD_PATH = "/planetary/apod"

_Translator = Callable[[dict[str, str]], Awaitable[dict[str, dict[str, str]]]] | None


def _today_utc() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def _is_today(target_date: str) -> bool:
    return target_date == _today_utc()


def _apod_from_payload(payload: dict, target_date: str) -> Apod:
    return Apod(
        date=payload.get("date", target_date),
        title=payload.get("title", ""),
        explanation=payload.get("explanation", ""),
        url=sanitise_url(payload.get("url")) or "",
        hdurl=sanitise_url(payload.get("hdurl")),
        media_type=payload.get("media_type", "image"),
        copyright=payload.get("copyright"),
        thumbnail_url=sanitise_url(payload.get("thumbnail_url")),
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


async def _fill_translations(session: AsyncSession, row: Apod, translator: Any) -> None:
    """Translate title + explanation and persist to translations_json."""
    try:
        i18n = await translator({"title": row.title, "explanation": row.explanation})
        row.translations_json = json.dumps(i18n, ensure_ascii=False)
        await session.commit()
    except Exception as exc:  # noqa: BLE001
        logger.warning("APOD translation failed for %s: %s", row.date, exc)


class ApodResult:
    def __init__(self, row: Apod, cached: bool, stale: bool, is_today: bool) -> None:
        self.row = row
        self.cached = cached
        self.stale = stale
        self.is_today = is_today


def _validate_date(target_date: str) -> date:
    return date.fromisoformat(target_date)


async def fetch_apod(
    session: AsyncSession,
    client: NasaClient,
    target_date: str,
    translator: _Translator = None,
) -> ApodResult:
    """Return APOD for ``target_date`` (YYYY-MM-DD) applying the caching policy."""
    parsed = _validate_date(target_date)
    is_today = _is_today(parsed.isoformat())

    existing = await session.get(Apod, parsed.isoformat())

    if existing is not None and not is_today:
        # Historical cache hit — translate only if translations are missing
        if translator is not None and existing.translations_json is None:
            await _fill_translations(session, existing, translator)
        return ApodResult(existing, cached=True, stale=False, is_today=False)

    try:
        payload = await client.get(APOD_PATH, params={"date": parsed.isoformat()})
    except NasaClientError:
        if existing is not None:
            return ApodResult(existing, cached=True, stale=True, is_today=is_today)
        raise

    row = await _upsert(session, parsed.isoformat(), payload)

    # Always (re-)translate freshly fetched content
    if translator is not None:
        await _fill_translations(session, row, translator)

    return ApodResult(row, cached=False, stale=False, is_today=is_today)
