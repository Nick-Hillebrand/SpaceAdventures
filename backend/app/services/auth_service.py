"""Authentication service — passwords, JWTs, OTPs, login rate-limiting."""
from __future__ import annotations

import hashlib
import logging
import secrets
from datetime import datetime, timedelta, timezone

import jwt
from passlib.context import CryptContext
from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.models.notification_log import NotificationLog
from app.models.subscription import Subscription
from app.models.user import LoginAttempt, Otp, RefreshToken, User

logger = logging.getLogger(__name__)

# P7: CryptContext defined ONCE at module level — never inside a function
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto", bcrypt__rounds=12)

# Dummy hash used for constant-time verification when user not found
_DUMMY_HASH = pwd_context.hash("dummy-password-for-timing")

# Rate-limit thresholds
_MAX_LOGIN_ATTEMPTS = 5
_LOGIN_WINDOW_SECONDS = 900  # 15 minutes
_MAX_OTP_RESENDS = 5
_OTP_RESEND_WINDOW_SECONDS = 3600  # 1 hour
_OTP_TTL_SECONDS = 600  # 10 minutes
_MAX_OTP_FAILURES = 5


def _log_otp_stub(user_id: int, channel: str, code: str, settings: Settings) -> None:
    """Stub OTP 'delivery' via log line.

    The plaintext code is only written to the log in dev/test
    (require_secrets=False); production logs must never contain OTPs.
    """
    if settings.require_secrets:
        logger.info("OTP generated for user %s channel=%s (stub — not sent)", user_id, channel)
    else:
        logger.info("OTP for user %s %s: %s (stub — not sent)", user_id, channel, code)


# ---------------------------------------------------------------------------
# Password helpers
# ---------------------------------------------------------------------------

def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


# ---------------------------------------------------------------------------
# JWT helpers
# ---------------------------------------------------------------------------

def create_access_token(user_id: int, settings: Settings) -> str:
    now = datetime.now(timezone.utc)
    expire = now + timedelta(seconds=settings.access_token_ttl_seconds)
    payload = {
        "sub": str(user_id),
        "exp": expire,
        "iat": now,
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def create_refresh_token_raw() -> str:
    return secrets.token_urlsafe(32)


def hash_refresh_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def decode_access_token(token: str, settings: Settings) -> dict:
    """Decode and verify an access token. Raises jwt.PyJWTError on any failure."""
    # P8/P1.3: verify_exp is on by default, but require exp+sub explicitly —
    # a token missing either claim must be rejected, not silently accepted.
    return jwt.decode(
        token,
        settings.jwt_secret_key,
        algorithms=[settings.jwt_algorithm],
        options={"require": ["exp", "sub"]},
    )


# ---------------------------------------------------------------------------
# OTP helpers
# ---------------------------------------------------------------------------

def generate_otp() -> str:
    """Return a 6-digit zero-padded OTP string."""
    return f"{secrets.randbelow(1_000_000):06d}"


def hash_otp(code: str) -> str:
    return pwd_context.hash(code)


def verify_otp_code(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


# ---------------------------------------------------------------------------
# Login rate-limit helpers
# ---------------------------------------------------------------------------

def sha256_identifier(identifier: str) -> str:
    return hashlib.sha256(identifier.encode()).hexdigest()


# ---------------------------------------------------------------------------
# DB operations
# ---------------------------------------------------------------------------

async def register_user(session: AsyncSession, data: dict, settings: Settings) -> User:
    """Create a new user and generate OTPs for each provided channel.

    Raises ValueError("REGISTRATION_FAILED") on duplicate email/phone.
    """
    password_hash = hash_password(data["password"])
    user = User(
        first_name=data["first_name"],
        last_name=data["last_name"],
        email=data.get("email"),
        phone=data.get("phone"),
        password_hash=password_hash,
    )
    if data.get("consent_notifications"):
        user.consent_notifications_at = datetime.now(timezone.utc)
        user.consent_source = "register-form-v1"
    session.add(user)
    try:
        await session.flush()  # get user.id; will raise on unique violation
    except Exception as exc:
        await session.rollback()
        logger.warning("Registration failed: %s", exc)
        raise ValueError("REGISTRATION_FAILED") from exc

    now = datetime.now(timezone.utc)
    expires = now + timedelta(seconds=_OTP_TTL_SECONDS)

    if data.get("email"):
        code = generate_otp()
        otp = Otp(
            user_id=user.id,
            channel="email",
            code_hash=hash_otp(code),
            expires_at=expires,
        )
        session.add(otp)
        _log_otp_stub(user.id, "email", code, settings)

    if data.get("phone"):
        code = generate_otp()
        otp = Otp(
            user_id=user.id,
            channel="phone",
            code_hash=hash_otp(code),
            expires_at=expires,
        )
        session.add(otp)
        _log_otp_stub(user.id, "phone", code, settings)

    await session.commit()
    await session.refresh(user)
    return user


async def set_consent(session: AsyncSession, user: User, granted: bool) -> User:
    """Grant or withdraw notification consent (P1.9, AccountPage toggle)."""
    if granted:
        user.consent_notifications_at = datetime.now(timezone.utc)
        user.consent_source = "account-settings-v1"
    else:
        user.consent_notifications_at = None
        user.consent_source = None
    await session.commit()
    await session.refresh(user)
    return user


async def set_pro_status(session: AsyncSession, user_id: int, is_pro: bool) -> User | None:
    """Admin-only Pro grant/revoke (20-location-and-sky-alerts.md L1).

    No billing integration exists yet, so Pro status is toggled manually by
    an operator via the admin API key rather than a webhook. Returns None if
    `user_id` doesn't exist.
    """
    user = await session.get(User, user_id)
    if user is None:
        return None
    user.is_pro = is_pro
    await session.commit()
    await session.refresh(user)
    return user


async def delete_account(session: AsyncSession, user: User, password: str) -> None:
    """Hard-delete a user's account (P1.10, GDPR/PIPEDA).

    Raises ValueError("INVALID_PASSWORD") without deleting anything.
    notification_log rows are anonymized (user_id -> NULL), not deleted —
    they are billing/audit records; this must happen before the user row is
    deleted so the FK's ON DELETE CASCADE never touches them.
    """
    if not verify_password(password, user.password_hash):
        raise ValueError("INVALID_PASSWORD")

    await session.execute(
        update(NotificationLog)
        .where(NotificationLog.user_id == user.id)
        .values(user_id=None)
    )
    await session.delete(user)
    await session.commit()


async def export_account(session: AsyncSession, user: User) -> dict:
    """Return a JSON-serializable export of a user's data (P1.10).

    No password hash, no refresh-token hashes — only what the export spec
    calls for: profile, subscriptions, notification history.
    """
    sub_result = await session.execute(
        select(Subscription).where(Subscription.user_id == user.id)
    )
    subscriptions = list(sub_result.scalars().all())

    log_result = await session.execute(
        select(NotificationLog).where(NotificationLog.user_id == user.id)
    )
    notification_history = list(log_result.scalars().all())

    return {
        "profile": {
            "id": user.id,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "email": user.email,
            "phone": user.phone,
            "email_verified": user.email_verified,
            "phone_verified": user.phone_verified,
            "created_at": user.created_at.isoformat(),
            "consent_notifications_at": (
                user.consent_notifications_at.isoformat()
                if user.consent_notifications_at
                else None
            ),
            "is_pro": user.is_pro,
            "location_name": user.location_name,
            "location_lat": user.location_lat,
            "location_lng": user.location_lng,
            "location_tz": user.location_tz,
            "ical_token": user.ical_token,
        },
        "subscriptions": [
            {
                "id": s.id,
                "type": s.type,
                "ll2_id": s.ll2_id,
                "agency_name": s.agency_name,
                "notify_email": s.notify_email,
                "notify_sms": s.notify_sms,
                "created_at": s.created_at.isoformat(),
            }
            for s in subscriptions
        ],
        "notification_history": [
            {
                "ll2_id": n.ll2_id,
                "iss_pass_alert_id": n.iss_pass_alert_id,
                "change_type": n.change_type,
                "channel": n.channel,
                "delivery_status": n.delivery_status,
                "sent_at": n.sent_at.isoformat(),
            }
            for n in notification_history
        ],
    }


async def verify_otp(
    session: AsyncSession,
    user_id: int,
    channel: str,
    code: str,
) -> bool:
    """Atomically verify an OTP.

    Returns True on success, False on failure.
    Increments failed_attempts; deletes OTP row after _MAX_OTP_FAILURES wrong tries.

    # CONCURRENCY: requires Postgres row lock in multi-worker deployments —
    # locks the user row (a no-op on SQLite) as the serialization point for
    # concurrent verification attempts (17-worker-and-scheduling.md P3.3).
    """
    user_result = await session.execute(
        select(User).where(User.id == user_id).with_for_update()
    )
    user = user_result.scalar_one_or_none()

    result = await session.execute(
        select(Otp).where(
            Otp.user_id == user_id,
            Otp.channel == channel,
            Otp.used == False,  # noqa: E712
        ).order_by(Otp.created_at.desc()).limit(1)
    )
    otp = result.scalar_one_or_none()

    if otp is None:
        return False

    now = datetime.now(timezone.utc)
    otp_expires = otp.expires_at
    # Ensure timezone-aware comparison
    if otp_expires.tzinfo is None:
        otp_expires = otp_expires.replace(tzinfo=timezone.utc)
    if otp_expires < now:
        return False

    if not verify_otp_code(code, otp.code_hash):
        otp.failed_attempts += 1
        if otp.failed_attempts >= _MAX_OTP_FAILURES:
            await session.delete(otp)
        await session.commit()
        return False

    # Success
    otp.used = True
    if user is not None:
        if channel == "email":
            user.email_verified = True
        elif channel == "phone":
            user.phone_verified = True
    await session.commit()
    return True


async def resend_otp(
    session: AsyncSession,
    user_id: int,
    channel: str,
    settings: Settings,
) -> None:
    """Rate-limited OTP resend. Raises ValueError("OTP_RATE_LIMIT") if exceeded.

    # CONCURRENCY: requires Postgres row lock in multi-worker deployments —
    # locks the user row (a no-op on SQLite) as the serialization point for
    # the rate-limit count check (17-worker-and-scheduling.md P3.3).
    """
    await session.execute(select(User).where(User.id == user_id).with_for_update())

    window_start = datetime.now(timezone.utc) - timedelta(seconds=_OTP_RESEND_WINDOW_SECONDS)
    result = await session.execute(
        select(func.count()).select_from(Otp).where(
            Otp.user_id == user_id,
            Otp.channel == channel,
            Otp.created_at >= window_start,
        )
    )
    count = result.scalar_one()
    if count > _MAX_OTP_RESENDS:
        raise ValueError("OTP_RATE_LIMIT")

    now = datetime.now(timezone.utc)
    expires = now + timedelta(seconds=_OTP_TTL_SECONDS)
    code = generate_otp()
    otp = Otp(
        user_id=user_id,
        channel=channel,
        code_hash=hash_otp(code),
        expires_at=expires,
    )
    session.add(otp)
    await session.commit()
    _log_otp_stub(user_id, channel, code, settings)


async def login(
    session: AsyncSession,
    email_or_phone: str,
    password: str,
    ip_address: str,
    settings: Settings,
) -> tuple[str, str]:
    """Rate-limited login. Returns (access_token, refresh_token_raw).

    Raises ValueError("RATE_LIMITED") or ValueError("LOGIN_FAILED").
    """
    identifier_hash = sha256_identifier(email_or_phone)
    window_start = datetime.now(timezone.utc) - timedelta(seconds=_LOGIN_WINDOW_SECONDS)

    # Check rate limit
    result = await session.execute(
        select(func.count()).select_from(LoginAttempt).where(
            LoginAttempt.identifier == identifier_hash,
            LoginAttempt.failed_at >= window_start,
        )
    )
    attempt_count = result.scalar_one()
    if attempt_count >= _MAX_LOGIN_ATTEMPTS:
        raise ValueError("RATE_LIMITED")

    # Look up user (by email or phone)
    user_result = await session.execute(
        select(User).where(
            (User.email == email_or_phone) | (User.phone == email_or_phone)
        )
    )
    user = user_result.scalar_one_or_none()

    # Constant-time: always verify a password, even if user not found
    hash_to_check = user.password_hash if user is not None else _DUMMY_HASH
    password_ok = verify_password(password, hash_to_check)

    if user is None or not password_ok:
        # Record failed attempt
        attempt = LoginAttempt(
            identifier=identifier_hash,
            ip_address=ip_address,
        )
        session.add(attempt)
        await session.commit()

        # Check if this was the 5th (triggering) failure — send security alert stub
        new_count = attempt_count + 1
        if new_count >= _MAX_LOGIN_ATTEMPTS:
            logger.warning(
                "Security alert: %d failed login attempts for identifier hash %s from %s",
                new_count,
                identifier_hash,
                ip_address,
            )
        raise ValueError("LOGIN_FAILED")

    # Successful login — clear all prior failed attempts for this identifier
    await session.execute(
        delete(LoginAttempt).where(LoginAttempt.identifier == identifier_hash)
    )

    # Issue tokens
    access_token = create_access_token(user.id, settings)
    raw_refresh = create_refresh_token_raw()
    token_hash = hash_refresh_token(raw_refresh)
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=settings.refresh_token_ttl_seconds)

    refresh_token_row = RefreshToken(
        user_id=user.id,
        token_hash=token_hash,
        expires_at=expires_at,
    )
    session.add(refresh_token_row)
    await session.commit()

    return access_token, raw_refresh


async def refresh_tokens(
    session: AsyncSession,
    raw_refresh_token: str,
    settings: Settings,
) -> tuple[str, str]:
    """Rotate refresh tokens.

    Raises ValueError on invalid/revoked/expired token.

    # CONCURRENCY: requires Postgres row lock in multi-worker deployments —
    # SELECT ... FOR UPDATE on the refresh-token row (a no-op on SQLite) is
    # the only mechanism serializing concurrent rotation attempts
    # (17-worker-and-scheduling.md P3.3).
    """
    token_hash = hash_refresh_token(raw_refresh_token)

    result = await session.execute(
        select(RefreshToken).where(RefreshToken.token_hash == token_hash).with_for_update()
    )
    token_row = result.scalar_one_or_none()

    if token_row is None:
        raise ValueError("INVALID_REFRESH_TOKEN")

    if token_row.revoked:
        raise ValueError("REVOKED_REFRESH_TOKEN")

    now = datetime.now(timezone.utc)
    expires = token_row.expires_at
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    if expires < now:
        raise ValueError("EXPIRED_REFRESH_TOKEN")

    # Revoke old token
    token_row.revoked = True

    # Issue new tokens
    access_token = create_access_token(token_row.user_id, settings)
    new_raw = create_refresh_token_raw()
    new_hash = hash_refresh_token(new_raw)
    new_expires = now + timedelta(seconds=settings.refresh_token_ttl_seconds)

    new_token_row = RefreshToken(
        user_id=token_row.user_id,
        token_hash=new_hash,
        expires_at=new_expires,
    )
    session.add(new_token_row)
    await session.commit()

    return access_token, new_raw


async def logout(session: AsyncSession, raw_refresh_token: str) -> None:
    """Revoke a refresh token."""
    token_hash = hash_refresh_token(raw_refresh_token)
    result = await session.execute(
        select(RefreshToken).where(RefreshToken.token_hash == token_hash)
    )
    token_row = result.scalar_one_or_none()
    if token_row is None:
        raise ValueError("INVALID_REFRESH_TOKEN")
    token_row.revoked = True
    await session.commit()


async def get_current_user(
    session: AsyncSession,
    token: str,
    settings: Settings,
) -> User:
    """Decode JWT and load the corresponding user.

    Raises ValueError on any failure.
    """
    try:
        payload = decode_access_token(token, settings)
    except jwt.PyJWTError as exc:
        raise ValueError("INVALID_TOKEN") from exc

    user_id_str = payload.get("sub")
    if not user_id_str:
        raise ValueError("INVALID_TOKEN")

    try:
        user_id = int(user_id_str)
    except (TypeError, ValueError) as exc:
        raise ValueError("INVALID_TOKEN") from exc

    user = await session.get(User, user_id)
    if user is None:
        raise ValueError("USER_NOT_FOUND")
    return user
