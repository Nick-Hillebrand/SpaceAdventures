"""Web Push subscription CRUD (19-notification-channels-v2.md B1.2)."""

from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.push_subscription import PushSubscription
from app.schemas.push import PushSubscribeRequest


async def subscribe(
    session: AsyncSession, user_id: int, data: PushSubscribeRequest
) -> PushSubscription:
    """Upsert on `endpoint` — re-subscribing the same browser (e.g. after the
    push service rotates keys) must not create a duplicate row."""
    stmt = select(PushSubscription).where(PushSubscription.endpoint == data.endpoint)
    result = await session.execute(stmt)
    existing = result.scalar_one_or_none()

    if existing is not None:
        existing.user_id = user_id
        existing.p256dh = data.keys.p256dh
        existing.auth = data.keys.auth
        await session.commit()
        await session.refresh(existing)
        return existing

    sub = PushSubscription(
        user_id=user_id,
        endpoint=data.endpoint,
        p256dh=data.keys.p256dh,
        auth=data.keys.auth,
    )
    session.add(sub)
    await session.commit()
    await session.refresh(sub)
    return sub


async def unsubscribe(session: AsyncSession, user_id: int, endpoint: str) -> None:
    """Delete-by-endpoint, scoped to the caller's own `user_id`.

    Returns 404 for both "not found" and "wrong user" to prevent IDOR, same
    pattern as `subscription_service.delete_subscription`.
    """
    stmt = select(PushSubscription).where(
        PushSubscription.endpoint == endpoint,
        PushSubscription.user_id == user_id,
    )
    result = await session.execute(stmt)
    sub = result.scalar_one_or_none()
    if sub is None:
        raise HTTPException(
            status_code=404,
            detail={"error": {"code": "NOT_FOUND", "message": "Push subscription not found"}},
        )
    await session.delete(sub)
    await session.commit()
