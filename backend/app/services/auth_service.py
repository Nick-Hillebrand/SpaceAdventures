"""Authentication service — passwords, JWTs, OTPs, login rate-limiting."""
from __future__ import annotations

import asyncio
import hashlib
import logging
import secrets
from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.models.user import LoginAttempt, Otp, RefreshToken, User

logger = logging.getLogger(__name__)

# P7: CryptContext defined ONCE at module level — never inside a function
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto", bcrypt__rounds=12)

# P10: module-level lock for refresh token rotation
_REFRESH_LOCK: asyncio.Lock = asyncio.Lock()

# P9: module-level lock for OTP rate-limit check
_OTP_LOCK: asyncio.Lock = asyncio.Lock()

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
    """Decode and verify an access token. Raises JWTError on any failure."""
    # P8: ALWAYS pass options={"verify_exp": True} explicitly
    return jwt.decode(
        token,
        settings.jwt_secret_key,
        algorithms=[settings.jwt_algorithm],
        options={"verify_exp": True},
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


async def verify_otp(
    session: AsyncSession,
    user_id: int,
    channel: str,
    code: str,
) -> bool:
    """Atomically verify an OTP.

    Returns True on success, False on failure.
    Increments failed_attempts; deletes OTP row after _MAX_OTP_FAILURES wrong tries.
    """
    async with _OTP_LOCK:
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
        user = await session.get(User, user_id)
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
    """Rate-limited OTP resend. Raises ValueError("OTP_RATE_LIMIT") if exceeded."""
    # P9: atomic check under lock
    async with _OTP_LOCK:
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
    """Rotate refresh tokens (P10: uses _REFRESH_LOCK).

    Raises ValueError on invalid/revoked/expired token.
    """
    token_hash = hash_refresh_token(raw_refresh_token)

    async with _REFRESH_LOCK:
        result = await session.execute(
            select(RefreshToken).where(RefreshToken.token_hash == token_hash)
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
    except JWTError as exc:
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
