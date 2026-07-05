from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas.neo import NeoData, NeoFeedResponse
from app.services import neo_service
from app.services.nasa_client import NasaClient

router = APIRouter(prefix="/api/v1/neo", tags=["neo"])


def _get_nasa_client(request: Request) -> NasaClient:
    client = getattr(request.app.state, "nasa_client", None)
    if client is None:
        raise HTTPException(status_code=503, detail="NASA client not initialised")
    return client


@router.get("/feed", response_model=NeoFeedResponse)
async def get_neo_feed(
    start: str = Query(..., description="YYYY-MM-DD"),
    end: str = Query(..., description="YYYY-MM-DD; at most 7 days after start"),
    session: AsyncSession = Depends(get_db),
    client: NasaClient = Depends(_get_nasa_client),
) -> NeoFeedResponse:
    try:
        result = await neo_service.fetch_neo_feed(session, client, start, end)
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail={"error": {"code": "INVALID_RANGE", "message": str(exc)}},
        )
    return NeoFeedResponse(
        data=[NeoData.model_validate(row) for row in result.rows],
        cached=result.cached,
        stale=result.stale,
        fetched_at=result.fetched_at,
        is_today=result.is_today,
    )
