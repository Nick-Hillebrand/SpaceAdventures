"""IP-level rate limiting (P1.6).

Sliding-window limiter backed by `rate_limit_events` so it works correctly
across multiple web worker processes — an in-process dict would not (see
17-worker-and-scheduling.md). Buckets are independent: `auth` guards
login/register/refresh against credential-stuffing, `otp_send` additionally
guards every OTP-issuing route, since each SMS costs money regardless of how
many logins/registrations triggered it (this bucket is mandatory, not
optional).

Unlike account-level throttling (`auth_service.login`'s `LoginAttempt`
check), which keys on a hash of the email/phone, this keys on a hash of the
client IP — never the raw IP — so it also catches distributed attempts
against many different accounts from the same source.
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.rate_limit import RateLimitEvent

AUTH_BUCKET = "auth"
AUTH_LIMIT = 30
AUTH_WINDOW_SECONDS = 900  # 15 minutes

OTP_SEND_BUCKET = "otp_send"
OTP_SEND_LIMIT = 10
OTP_SEND_WINDOW_SECONDS = 3600  # 1 hour

GEOCODE_BUCKET = "geocode"
GEOCODE_LIMIT = 20
GEOCODE_WINDOW_SECONDS = 3600  # 1 hour


def get_client_ip(request: Request) -> str:
    """Client IP for rate-limiting purposes.

    `X-Forwarded-For` is honored only when `trust_proxy_headers` is set
    (true behind the Caddy reverse proxy in prod) — trusting it unconditionally
    would let any client spoof its rate-limit bucket via the header.
    """
    settings = request.app.state.settings
    if settings.trust_proxy_headers:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def hash_ip(ip_address: str) -> str:
    return hashlib.sha256(ip_address.encode()).hexdigest()


async def _check_and_record(
    session: AsyncSession, bucket: str, ip_hash: str, limit: int, window_seconds: int
) -> None:
    """Record this request and raise 429 if it exceeds `limit`.

    Sliding window: count rows in the window, insert this event, then check
    the pre-insert count against `limit` — so the request that pushes the
    bucket over the limit is itself recorded (keeping the window accurate)
    but rejected.

    Response body is identical for every caller regardless of which bucket
    or route tripped it, so a 429 never leaks which limit was hit.
    """
    window_start = datetime.now(timezone.utc) - timedelta(seconds=window_seconds)
    result = await session.execute(
        select(func.count()).select_from(RateLimitEvent).where(
            RateLimitEvent.bucket == bucket,
            RateLimitEvent.ip_hash == ip_hash,
            RateLimitEvent.created_at >= window_start,
        )
    )
    count = result.scalar_one()
    session.add(RateLimitEvent(bucket=bucket, ip_hash=ip_hash))
    await session.commit()
    if count >= limit:
        raise HTTPException(
            status_code=429,
            detail={
                "error": {
                    "code": "RATE_LIMITED",
                    "message": "Too many requests. Try again later.",
                }
            },
            headers={"Retry-After": str(window_seconds)},
        )


def rate_limiter(bucket: str, limit: int, window_seconds: int):
    """Dependency factory: returns a FastAPI dependency enforcing `bucket`."""

    async def _dependency(
        request: Request,
        session: AsyncSession = Depends(get_db),
    ) -> None:
        ip_hash = hash_ip(get_client_ip(request))
        await _check_and_record(session, bucket, ip_hash, limit, window_seconds)

    return _dependency


def user_rate_limiter(bucket: str, limit: int, window_seconds: int, get_current_user):
    """Like `rate_limiter`, but keyed on a hash of `"user:{id}"` rather than
    the client IP.

    Some abuse tracks the account, not the network — geocode search is cheap
    to hit from many IPs behind a shared NAT/VPN but is still one account's
    quota. Reuses the same `RateLimitEvent`/`ip_hash` column instead of
    adding a schema just for this; `get_current_user` is passed in (rather
    than imported) to avoid a circular import with `app.routers.auth`, which
    itself imports `rate_limiter` from this module.
    """

    async def _dependency(
        session: AsyncSession = Depends(get_db),
        current_user=Depends(get_current_user),
    ) -> None:
        key_hash = hash_ip(f"user:{current_user.id}")
        await _check_and_record(session, bucket, key_hash, limit, window_seconds)

    return _dependency


auth_rate_limit = rate_limiter(AUTH_BUCKET, AUTH_LIMIT, AUTH_WINDOW_SECONDS)
otp_send_rate_limit = rate_limiter(OTP_SEND_BUCKET, OTP_SEND_LIMIT, OTP_SEND_WINDOW_SECONDS)
