"""Auth router — registration, OTP, login, refresh, logout, me."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.database import get_db
from app.models.user import User
from app.schemas.auth import (
    LoginRequest,
    LogoutRequest,
    RefreshRequest,
    RegisterRequest,
    ResendOtpRequest,
    TokenResponse,
    UserResponse,
    VerifyOtpRequest,
)
from app.services import auth_service

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


# ---------------------------------------------------------------------------
# Dependencies
# ---------------------------------------------------------------------------


def get_settings_dep(request: Request) -> Settings:
    return request.app.state.settings


async def get_current_user_dep(
    authorization: str | None = Header(default=None),
    session: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
) -> User:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail={"error": {"code": "UNAUTHORIZED", "message": "Missing or invalid Authorization header"}})
    token = authorization[len("Bearer "):]
    try:
        user = await auth_service.get_current_user(session, token, settings)
    except ValueError:
        raise HTTPException(status_code=401, detail={"error": {"code": "UNAUTHORIZED", "message": "Invalid or expired token"}})
    return user


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.post("/register", status_code=201)
async def register(
    body: RegisterRequest,
    session: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
) -> JSONResponse:
    if not body.email and not body.phone:
        raise HTTPException(
            status_code=422,
            detail={"error": {"code": "VALIDATION_ERROR", "message": "At least one of email or phone is required"}},
        )
    data = {
        "first_name": body.first_name,
        "last_name": body.last_name,
        "email": body.email or None,
        "phone": body.phone or None,
        "password": body.password,
    }
    try:
        user = await auth_service.register_user(session, data, settings)
    except ValueError:
        # P21-like: return generic error — no enumeration of what failed
        return JSONResponse(
            status_code=422,
            content={"error": {"code": "REGISTRATION_FAILED", "message": "Please check your details and try again"}},
        )
    return JSONResponse(
        status_code=201,
        content={"id": user.id, "message": "Registration successful. Please check your OTP(s)."},
    )


@router.post("/verify/email")
async def verify_email(
    body: VerifyOtpRequest,
    current_user: User = Depends(get_current_user_dep),
    session: AsyncSession = Depends(get_db),
) -> JSONResponse:
    if current_user.email_verified:
        return JSONResponse(content={"message": "Already verified"})
    success = await auth_service.verify_otp(session, current_user.id, "email", body.otp)
    if not success:
        raise HTTPException(status_code=400, detail={"error": {"code": "INVALID_OTP", "message": "Invalid or expired OTP"}})
    return JSONResponse(content={"message": "Email verified"})


@router.post("/verify/phone")
async def verify_phone(
    body: VerifyOtpRequest,
    current_user: User = Depends(get_current_user_dep),
    session: AsyncSession = Depends(get_db),
) -> JSONResponse:
    if current_user.phone_verified:
        return JSONResponse(content={"message": "Already verified"})
    success = await auth_service.verify_otp(session, current_user.id, "phone", body.otp)
    if not success:
        raise HTTPException(status_code=400, detail={"error": {"code": "INVALID_OTP", "message": "Invalid or expired OTP"}})
    return JSONResponse(content={"message": "Phone verified"})


@router.post("/verify/resend")
async def resend_otp(
    body: ResendOtpRequest,
    current_user: User = Depends(get_current_user_dep),
    session: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
) -> JSONResponse:
    try:
        await auth_service.resend_otp(session, current_user.id, body.channel, settings)
    except ValueError as exc:
        if "RATE_LIMIT" in str(exc):
            raise HTTPException(
                status_code=429,
                detail={"error": {"code": "OTP_RATE_LIMIT", "message": "Too many OTP requests. Please try again later."}},
            )
        raise
    return JSONResponse(content={"message": "OTP resent"})


@router.post("/login")
async def login(
    body: LoginRequest,
    request: Request,
    session: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
) -> TokenResponse:
    ip_address = request.client.host if request.client else "unknown"
    try:
        access_token, raw_refresh = await auth_service.login(
            session, body.email_or_phone, body.password, ip_address, settings
        )
    except ValueError as exc:
        msg = str(exc)
        if msg == "RATE_LIMITED":
            return JSONResponse(
                status_code=429,
                content={"error": {"code": "RATE_LIMITED", "message": "Too many login attempts. Try again later."}},
                headers={"Retry-After": "900"},
            )
        raise HTTPException(
            status_code=401,
            detail={"error": {"code": "LOGIN_FAILED", "message": "Invalid credentials"}},
        )
    return TokenResponse(access_token=access_token, refresh_token=raw_refresh)


@router.post("/refresh")
async def refresh(
    body: RefreshRequest,
    session: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
) -> TokenResponse:
    try:
        access_token, new_refresh = await auth_service.refresh_tokens(
            session, body.refresh_token, settings
        )
    except ValueError:
        raise HTTPException(
            status_code=401,
            detail={"error": {"code": "INVALID_REFRESH_TOKEN", "message": "Invalid, revoked, or expired refresh token"}},
        )
    return TokenResponse(access_token=access_token, refresh_token=new_refresh)


@router.post("/logout")
async def logout(
    body: LogoutRequest,
    session: AsyncSession = Depends(get_db),
) -> JSONResponse:
    try:
        await auth_service.logout(session, body.refresh_token)
    except ValueError:
        raise HTTPException(
            status_code=401,
            detail={"error": {"code": "INVALID_REFRESH_TOKEN", "message": "Invalid refresh token"}},
        )
    return JSONResponse(content={"message": "Logged out"})


@router.get("/me", response_model=UserResponse)
async def me(
    current_user: User = Depends(get_current_user_dep),
) -> UserResponse:
    # NEVER return password_hash
    return UserResponse.model_validate(current_user)
