from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas.iss import (
    IssPassesResponse,
    IssPositionsResponse,
    IssQuotaResponse,
    IssTleResponse,
)
from app.services import iss_service
from app.services.n2yo_client import N2YOClient, N2YOError

router = APIRouter(prefix="/api/v1/iss", tags=["iss"])


def _get_n2yo_client(request: Request) -> N2YOClient:
    client = getattr(request.app.state, "n2yo_client", None)
    if client is None:
        raise HTTPException(status_code=503, detail="N2YO client not initialised")
    return client


def _get_cap(request: Request) -> int:
    return request.app.state.settings.n2yo_hourly_cap


def _validate_observer(lat: float, lng: float, alt: float) -> None:
    if not (-90 <= lat <= 90):
        raise HTTPException(
            status_code=400,
            detail={"error": {"code": "INVALID_PARAMS", "message": "lat must be in [-90, 90]"}},
        )
    if not (-180 <= lng <= 180):
        raise HTTPException(
            status_code=400,
            detail={"error": {"code": "INVALID_PARAMS", "message": "lng must be in [-180, 180]"}},
        )
    if not (0 <= alt <= 10000):
        raise HTTPException(
            status_code=400,
            detail={"error": {"code": "INVALID_PARAMS", "message": "alt must be in [0, 10000]"}},
        )


@router.get("/positions", response_model=IssPositionsResponse)
async def get_positions(
    session: AsyncSession = Depends(get_db),
    client: N2YOClient = Depends(_get_n2yo_client),
    cap: int = Depends(_get_cap),
) -> IssPositionsResponse:
    try:
        positions, fetched_at, cached, quota_exhausted = await iss_service.get_positions(
            session, client, cap
        )
    except N2YOError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail={"error": {"code": exc.code, "message": exc.message}},
        )
    return IssPositionsResponse(
        positions=positions,
        fetched_at=fetched_at,
        cached=cached,
        quota_exhausted=quota_exhausted,
    )


@router.get("/tle", response_model=IssTleResponse)
async def get_tle(
    session: AsyncSession = Depends(get_db),
    client: N2YOClient = Depends(_get_n2yo_client),
    cap: int = Depends(_get_cap),
) -> IssTleResponse:
    try:
        tle, cached, quota_exhausted = await iss_service.get_tle(session, client, cap)
    except N2YOError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail={"error": {"code": exc.code, "message": exc.message}},
        )
    return IssTleResponse(
        tle_line0=tle.tle_line0,
        tle_line1=tle.tle_line1,
        tle_line2=tle.tle_line2,
        fetched_at=tle.fetched_at,
        cached=cached,
        quota_exhausted=quota_exhausted,
    )


@router.get("/passes/visual", response_model=IssPassesResponse)
async def get_visual_passes(
    lat: float = Query(...),
    lng: float = Query(...),
    alt: float = Query(default=0.0),
    session: AsyncSession = Depends(get_db),
    client: N2YOClient = Depends(_get_n2yo_client),
    cap: int = Depends(_get_cap),
) -> IssPassesResponse:
    _validate_observer(lat, lng, alt)
    try:
        passes, fetched_at, cached, quota_exhausted = await iss_service.get_passes(
            session, client, cap, "visual", lat, lng, alt
        )
    except N2YOError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail={"error": {"code": exc.code, "message": exc.message}},
        )
    return IssPassesResponse(
        passes=passes,
        fetched_at=fetched_at,
        cached=cached,
        quota_exhausted=quota_exhausted,
    )


@router.get("/passes/radio", response_model=IssPassesResponse)
async def get_radio_passes(
    lat: float = Query(...),
    lng: float = Query(...),
    alt: float = Query(default=0.0),
    session: AsyncSession = Depends(get_db),
    client: N2YOClient = Depends(_get_n2yo_client),
    cap: int = Depends(_get_cap),
) -> IssPassesResponse:
    _validate_observer(lat, lng, alt)
    try:
        passes, fetched_at, cached, quota_exhausted = await iss_service.get_passes(
            session, client, cap, "radio", lat, lng, alt
        )
    except N2YOError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail={"error": {"code": exc.code, "message": exc.message}},
        )
    return IssPassesResponse(
        passes=passes,
        fetched_at=fetched_at,
        cached=cached,
        quota_exhausted=quota_exhausted,
    )


@router.get("/quota", response_model=IssQuotaResponse)
async def get_quota(
    session: AsyncSession = Depends(get_db),
    cap: int = Depends(_get_cap),
) -> IssQuotaResponse:
    quota = await iss_service.get_quota(session, cap)
    resets_at = quota.window_start + timedelta(hours=1)
    return IssQuotaResponse(
        used=quota.used,
        cap=cap,
        window_start=quota.window_start,
        resets_at=resets_at,
    )
