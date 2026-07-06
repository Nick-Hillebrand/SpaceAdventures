from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas.mars import MarsPhotoData, MarsPhotosResponse, RoverInfo, RoversResponse
from app.services import mars_service
from app.services.nasa_client import NasaClient

router = APIRouter(prefix="/api/v1/mars", tags=["mars"])


def _get_nasa_client(request: Request) -> NasaClient:
    client = getattr(request.app.state, "nasa_client", None)
    if client is None:
        raise HTTPException(status_code=503, detail="NASA client not initialised")
    return client


@router.get("/rovers", response_model=RoversResponse)
async def get_rovers() -> RoversResponse:
    return RoversResponse(
        data=[
            RoverInfo(name=name, cameras=cameras)
            for name, cameras in mars_service.ROVER_CAMERAS.items()
        ]
    )


@router.get("/photos", response_model=MarsPhotosResponse)
async def get_photos(
    rover: str = Query(..., description="Rover name"),
    sol: int | None = Query(default=None, description="Martian sol"),
    earth_date: str | None = Query(default=None, description="YYYY-MM-DD"),
    camera: str | None = Query(default=None, description="Camera abbreviation"),
    page: int = Query(default=1, ge=1, description="Page number (25 photos per page)"),
    session: AsyncSession = Depends(get_db),
    client: NasaClient = Depends(_get_nasa_client),
) -> MarsPhotosResponse:
    try:
        result = await mars_service.fetch_photos(
            session,
            client,
            rover,
            sol=sol,
            earth_date=earth_date,
            camera=camera,
            page=page,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail={"error": {"code": "INVALID_PARAMS", "message": str(exc)}},
        )
    return MarsPhotosResponse(
        data=[MarsPhotoData.model_validate(row) for row in result.rows],
        cached=result.cached,
        stale=result.stale,
        fetched_at=result.fetched_at,
        is_today=result.is_today,
    )
