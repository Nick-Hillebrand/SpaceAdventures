"""Subscription CRUD and unsubscribe-by-token logic."""

from __future__ import annotations

from fastapi import HTTPException
from jose import JWTError
from jose import jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.models.subscription import Subscription
from app.schemas.subscription import CreateSubscriptionRequest


async def get_subscriptions(session: AsyncSession, user_id: int) -> list[Subscription]:
    """Return all subscriptions belonging to *user_id*."""
    stmt = select(Subscription).where(Subscription.user_id == user_id)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def create_subscription(
    session: AsyncSession, user_id: int, data: CreateSubscriptionRequest
) -> Subscription:
    """Create and persist a new subscription."""
    sub = Subscription(
        user_id=user_id,
        type=data.type,
        ll2_id=data.ll2_id,
        agency_name=data.agency_name,
        notify_email=data.notify_email,
        notify_sms=data.notify_sms,
    )
    session.add(sub)
    await session.commit()
    await session.refresh(sub)
    return sub


async def delete_subscription(
    session: AsyncSession, subscription_id: str, user_id: int
) -> None:
    """Delete a subscription.

    Returns 404 for both "not found" and "wrong user" to prevent IDOR.
    """
    stmt = select(Subscription).where(
        Subscription.id == subscription_id,
        Subscription.user_id == user_id,
    )
    result = await session.execute(stmt)
    sub = result.scalar_one_or_none()
    if sub is None:
        raise HTTPException(status_code=404, detail={"error": {"code": "NOT_FOUND", "message": "Subscription not found"}})
    await session.delete(sub)
    await session.commit()


async def unsubscribe_by_token(
    session: AsyncSession, token: str, settings: Settings
) -> None:
    """Verify an unsubscribe JWT and delete the referenced subscription."""
    try:
        payload = jwt.decode(
            token,
            settings.unsubscribe_secret_key,
            algorithms=["HS256"],
            options={"verify_exp": True},
        )
    except JWTError as exc:
        raise HTTPException(
            status_code=400,
            detail={"error": {"code": "INVALID_TOKEN", "message": "Invalid or expired unsubscribe token"}},
        ) from exc

    sub_id = payload.get("subscription_id")
    user_id = payload.get("user_id")

    if not sub_id or user_id is None:
        raise HTTPException(
            status_code=400,
            detail={"error": {"code": "INVALID_TOKEN", "message": "Malformed unsubscribe token"}},
        )

    stmt = select(Subscription).where(
        Subscription.id == sub_id,
        Subscription.user_id == user_id,
    )
    result = await session.execute(stmt)
    sub = result.scalar_one_or_none()
    if sub is None:
        raise HTTPException(
            status_code=404,
            detail={"error": {"code": "NOT_FOUND", "message": "Subscription not found"}},
        )

    await session.delete(sub)
    await session.commit()
