from __future__ import annotations

from datetime import datetime, timezone

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


@router.get("", response_model=ApodResponse)
async def get_apod(
    date: str | None = Query(default=None, description="YYYY-MM-DD; defaults to today (UTC)"),
    session: AsyncSession = Depends(get_db),
    client: NasaClient = Depends(_get_nasa_client),
) -> ApodResponse:
    target_date = date or datetime.now(timezone.utc).date().isoformat()
    try:
        result = await apod_service.fetch_apod(session, client, target_date)
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
    return ApodResponse(
        data=ApodData.model_validate(result.row),
        cached=result.cached,
        stale=result.stale,
        fetched_at=result.row.fetched_at,
        is_today=result.is_today,
    )
