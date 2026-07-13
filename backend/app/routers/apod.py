from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas.apod import ApodData, ApodResponse
from app.services import apod_service
from app.services.nasa_client import NasaClient

router = APIRouter(prefix="/api/v1/apod", tags=["apod"])


def _get_nasa_client(request: Request) -> NasaClient:
    client = getattr(request.app.state, "nasa_client", None)
    if client is None:
        raise HTTPException(status_code=503, detail="NASA client not initialised")
    return client


def _get_translator(request: Request) -> Any:
    return getattr(request.app.state, "translator", None)


def _apply_translations(data: ApodData, translations: dict | None, lang: str) -> ApodData:
    if lang == "en" or not translations:
        return data
    lang_data = translations.get(lang, {})
    if not lang_data:
        return data
    return data.model_copy(update={
        "title": lang_data.get("title", data.title),
        "explanation": lang_data.get("explanation", data.explanation),
    })


@router.get("", response_model=ApodResponse)
async def get_apod(
    date: str | None = Query(default=None, description="YYYY-MM-DD; defaults to today (UTC)"),
    lang: str = Query(default="en", description="ISO 639-1 language code"),
    session: AsyncSession = Depends(get_db),
    client: NasaClient = Depends(_get_nasa_client),
    translator: Any = Depends(_get_translator),
) -> ApodResponse:
    target_date = date or datetime.now(timezone.utc).date().isoformat()
    try:
        result = await apod_service.fetch_apod(session, client, target_date, translator=translator)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail={
                "error": {
                    "code": "INVALID_DATE",
                    "message": "date must be YYYY-MM-DD",
                }
            },
        )
    base_data = ApodData.model_validate(result.row)
    translated_data = _apply_translations(base_data, result.row.translations_json, lang)
    return ApodResponse(
        data=translated_data,
        cached=result.cached,
        stale=result.stale,
        fetched_at=result.row.fetched_at,
        is_today=result.is_today,
    )
