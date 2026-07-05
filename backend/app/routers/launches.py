from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas.launches import LaunchOut, LaunchesResponse
from app.services import launches_service
from app.services.ll2_client import LL2Client

router = APIRouter(prefix="/api/v1/launches", tags=["launches"])

_bearer = HTTPBearer(auto_error=False)


def _get_ll2_client(request: Request) -> LL2Client:
    client = getattr(request.app.state, "ll2_client", None)
    if client is None:
        raise HTTPException(status_code=503, detail="LL2 client not initialised")
    return client


def _require_admin(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> None:
    settings = request.app.state.settings
    if not settings.admin_api_key:
        raise HTTPException(status_code=503, detail="Admin API key not configured")
    expected = f"Bearer {settings.admin_api_key}"
    auth_header = request.headers.get("Authorization", "")
    if auth_header != expected:
        raise HTTPException(status_code=401, detail="Unauthorized")


@router.get("/upcoming", response_model=LaunchesResponse)
async def get_upcoming_launches(
    session: AsyncSession = Depends(get_db),
) -> LaunchesResponse:
    launches, last_synced_at = await launches_service.get_upcoming_launches(session)
    return LaunchesResponse(
        data=[LaunchOut.model_validate(launch) for launch in launches],
        last_synced_at=last_synced_at,
        cached=True,
    )


@router.post("/sync", status_code=200)
async def sync_launches(
    session: AsyncSession = Depends(get_db),
    ll2_client: LL2Client = Depends(_get_ll2_client),
    _admin: None = Depends(_require_admin),
) -> dict[str, str]:
    await launches_service.sync_launches(session, ll2_client)
    return {"status": "ok"}
