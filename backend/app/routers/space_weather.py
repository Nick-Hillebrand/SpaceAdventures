from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas.space_weather import SpaceWeatherEventData, SpaceWeatherResponse
from app.services import space_weather_service
from app.services.space_weather_service import EventType
from app.services.nasa_client import NasaClient

router = APIRouter(prefix="/api/v1/space-weather", tags=["space-weather"])


def _get_nasa_client(request: Request) -> NasaClient:
    client = getattr(request.app.state, "nasa_client", None)
    if client is None:
        raise HTTPException(status_code=503, detail="NASA client not initialised")
    return client


async def _handle(
    event_type: EventType,
    start: str,
    end: str,
    session: AsyncSession,
    client: NasaClient,
) -> SpaceWeatherResponse:
    try:
        result = await space_weather_service.fetch_events(session, client, event_type, start, end)
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail={"error": {"code": "INVALID_RANGE", "message": str(exc)}},
        )
    return SpaceWeatherResponse(
        data=[SpaceWeatherEventData.model_validate(row) for row in result.rows],
        cached=result.cached,
        stale=result.stale,
        fetched_at=result.fetched_at,
        is_today=result.is_today,
    )


@router.get("/flares", response_model=SpaceWeatherResponse)
async def get_flares(
    start: str = Query(..., description="YYYY-MM-DD"),
    end: str = Query(..., description="YYYY-MM-DD"),
    session: AsyncSession = Depends(get_db),
    client: NasaClient = Depends(_get_nasa_client),
) -> SpaceWeatherResponse:
    return await _handle("FLR", start, end, session, client)


@router.get("/storms", response_model=SpaceWeatherResponse)
async def get_storms(
    start: str = Query(..., description="YYYY-MM-DD"),
    end: str = Query(..., description="YYYY-MM-DD"),
    session: AsyncSession = Depends(get_db),
    client: NasaClient = Depends(_get_nasa_client),
) -> SpaceWeatherResponse:
    return await _handle("GST", start, end, session, client)


@router.get("/cmes", response_model=SpaceWeatherResponse)
async def get_cmes(
    start: str = Query(..., description="YYYY-MM-DD"),
    end: str = Query(..., description="YYYY-MM-DD"),
    session: AsyncSession = Depends(get_db),
    client: NasaClient = Depends(_get_nasa_client),
) -> SpaceWeatherResponse:
    return await _handle("CME", start, end, session, client)


@router.get("/sep", response_model=SpaceWeatherResponse)
async def get_sep(
    start: str = Query(..., description="YYYY-MM-DD"),
    end: str = Query(..., description="YYYY-MM-DD"),
    session: AsyncSession = Depends(get_db),
    client: NasaClient = Depends(_get_nasa_client),
) -> SpaceWeatherResponse:
    return await _handle("SEP", start, end, session, client)


@router.get("/rbe", response_model=SpaceWeatherResponse)
async def get_rbe(
    start: str = Query(..., description="YYYY-MM-DD"),
    end: str = Query(..., description="YYYY-MM-DD"),
    session: AsyncSession = Depends(get_db),
    client: NasaClient = Depends(_get_nasa_client),
) -> SpaceWeatherResponse:
    return await _handle("RBE", start, end, session, client)
