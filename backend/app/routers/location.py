"""Sky-location endpoints (20-location-and-sky-alerts.md).

All three routes require auth — a user's saved location is PII (home
coordinates), and the geocode search is proxied server-side so Open-Meteo's
response never reaches the browser unvalidated (25-security-testing.md §2.5).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User
from app.rate_limit import GEOCODE_BUCKET, GEOCODE_LIMIT, GEOCODE_WINDOW_SECONDS, user_rate_limiter
from app.routers.auth import get_current_user_dep
from app.schemas.location import LocationOut, LocationSearchResponse, SetLocationRequest
from app.services import location_service
from app.services.geocode_client import GeocodeClient, GeocodeClientError

router = APIRouter(prefix="/api/v1/location", tags=["location"])

geocode_rate_limit = user_rate_limiter(
    GEOCODE_BUCKET, GEOCODE_LIMIT, GEOCODE_WINDOW_SECONDS, get_current_user_dep
)


def _get_geocode_client(request: Request) -> GeocodeClient:
    client = getattr(request.app.state, "geocode_client", None)
    if client is None:
        raise HTTPException(status_code=503, detail="Geocode client not initialised")
    return client


@router.get(
    "/search",
    response_model=LocationSearchResponse,
    dependencies=[Depends(geocode_rate_limit)],
)
async def search_location(
    q: str = Query(..., min_length=1, max_length=200),
    current_user: User = Depends(get_current_user_dep),
    client: GeocodeClient = Depends(_get_geocode_client),
) -> LocationSearchResponse:
    try:
        candidates = await location_service.search_location(client, q)
    except GeocodeClientError as exc:
        raise location_service.geocode_error_response(exc)
    return LocationSearchResponse(candidates=candidates)


@router.post("", response_model=LocationOut)
async def set_location(
    body: SetLocationRequest,
    current_user: User = Depends(get_current_user_dep),
    session: AsyncSession = Depends(get_db),
) -> LocationOut:
    user = await location_service.set_location(session, current_user, body)
    return LocationOut.model_validate(user)


@router.delete("", status_code=204)
async def clear_location(
    current_user: User = Depends(get_current_user_dep),
    session: AsyncSession = Depends(get_db),
) -> Response:
    await location_service.clear_location(session, current_user)
    return Response(status_code=204)
