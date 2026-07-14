"""Web Push endpoints (19-notification-channels-v2.md B1.2)."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.database import get_db
from app.models.user import User
from app.routers.auth import get_current_user_dep, get_settings_dep
from app.schemas.push import PushSubscribeRequest, PushUnsubscribeRequest, VapidPublicKeyOut
from app.services import push_service

router = APIRouter(prefix="/api/v1/push", tags=["push"])


@router.get("/vapid-public-key", response_model=VapidPublicKeyOut)
async def vapid_public_key(settings: Settings = Depends(get_settings_dep)) -> VapidPublicKeyOut:
    return VapidPublicKeyOut(public_key=settings.vapid_public_key)


@router.post("/subscribe", status_code=204, response_model=None)
async def subscribe(
    body: PushSubscribeRequest,
    current_user: User = Depends(get_current_user_dep),
    session: AsyncSession = Depends(get_db),
) -> None:
    await push_service.subscribe(session, current_user.id, body)


@router.delete("/subscribe", status_code=204, response_model=None)
async def unsubscribe(
    body: PushUnsubscribeRequest,
    current_user: User = Depends(get_current_user_dep),
    session: AsyncSession = Depends(get_db),
) -> None:
    await push_service.unsubscribe(session, current_user.id, body.endpoint)
