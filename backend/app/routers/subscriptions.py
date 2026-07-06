"""Subscription endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.database import get_db
from app.models.user import User
from app.routers.auth import get_current_user_dep, get_settings_dep
from app.schemas.subscription import (
    CreateSubscriptionRequest,
    SubscriptionOut,
    UnsubscribeRequest,
)
from app.services import subscription_service

router = APIRouter(prefix="/api/v1/subscriptions", tags=["subscriptions"])


@router.get("", response_model=list[SubscriptionOut])
async def list_subscriptions(
    current_user: User = Depends(get_current_user_dep),
    session: AsyncSession = Depends(get_db),
) -> list[SubscriptionOut]:
    subs = await subscription_service.get_subscriptions(session, current_user.id)
    return [SubscriptionOut.model_validate(s) for s in subs]


# IMPORTANT: /unsubscribe MUST be registered before /{id} to avoid routing conflict.
@router.post("/unsubscribe")
async def unsubscribe(
    body: UnsubscribeRequest,
    session: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
) -> JSONResponse:
    await subscription_service.unsubscribe_by_token(session, body.token, settings)
    return JSONResponse(content={"message": "Unsubscribed successfully"})


@router.post("", status_code=201, response_model=SubscriptionOut)
async def create_subscription(
    body: CreateSubscriptionRequest,
    current_user: User = Depends(get_current_user_dep),
    session: AsyncSession = Depends(get_db),
) -> SubscriptionOut:
    sub = await subscription_service.create_subscription(session, current_user.id, body)
    return SubscriptionOut.model_validate(sub)


@router.delete("/{subscription_id}", status_code=204, response_model=None)
async def delete_subscription(
    subscription_id: str,
    current_user: User = Depends(get_current_user_dep),
    session: AsyncSession = Depends(get_db),
) -> None:
    await subscription_service.delete_subscription(session, subscription_id, current_user.id)
