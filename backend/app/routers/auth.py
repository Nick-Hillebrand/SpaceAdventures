"""Auth router — registration, OTP, login, refresh, logout, me.

P1.4 CSRF note: the refresh token lives in a cookie scoped
`SameSite=Strict; Path=/api/v1/auth`. SameSite=Strict means the cookie is
never sent on a cross-site request (including top-level navigations), so a
malicious site cannot trigger a credentialed /refresh call in the first
place. Even setting that aside, /refresh is a POST whose success response is
a *new access token in the JSON body* — a cross-site attacker can cause the
request to fire (absent SameSite) but cannot read the response due to CORS,
so forging the call gains them nothing. No CSRF token is needed.
"""
from __future__ import annotations

from fastapi import APIRouter, Body, Depends, Header, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.database import get_db
from app.models.user import User
from app.rate_limit import auth_rate_limit, otp_send_rate_limit
from app.schemas.auth import (
    ConsentRequest,
    DeleteAccountRequest,
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

REFRESH_COOKIE_NAME = "sa_refresh"
REFRESH_COOKIE_PATH = "/api/v1/auth"


def _set_refresh_cookie(response: Response, raw_refresh: str, settings: Settings) -> None:
    response.set_cookie(
        key=REFRESH_COOKIE_NAME,
        value=raw_refresh,
        max_age=settings.refresh_token_ttl_seconds,
        path=REFRESH_COOKIE_PATH,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="strict",
    )


def _clear_refresh_cookie(response: Response, settings: Settings) -> None:
    response.delete_cookie(
        key=REFRESH_COOKIE_NAME,
        path=REFRESH_COOKIE_PATH,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="strict",
    )


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


@router.post(
    "/register",
    status_code=201,
    dependencies=[Depends(auth_rate_limit), Depends(otp_send_rate_limit)],
)
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
        "consent_notifications": body.consent_notifications,
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


@router.post("/verify/resend", dependencies=[Depends(otp_send_rate_limit)])
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


@router.post("/login", dependencies=[Depends(auth_rate_limit)])
async def login(
    body: LoginRequest,
    request: Request,
    response: Response,
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
    _set_refresh_cookie(response, raw_refresh, settings)
    return TokenResponse(access_token=access_token)


@router.post("/refresh", dependencies=[Depends(auth_rate_limit)])
async def refresh(
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
    body: RefreshRequest | None = Body(default=None),
) -> TokenResponse:
    body_token = body.refresh_token if body else None
    raw_refresh = request.cookies.get(REFRESH_COOKIE_NAME) or body_token
    if not raw_refresh:
        raise HTTPException(
            status_code=401,
            detail={"error": {"code": "INVALID_REFRESH_TOKEN", "message": "Invalid, revoked, or expired refresh token"}},
        )
    try:
        access_token, new_refresh = await auth_service.refresh_tokens(
            session, raw_refresh, settings
        )
    except ValueError:
        raise HTTPException(
            status_code=401,
            detail={"error": {"code": "INVALID_REFRESH_TOKEN", "message": "Invalid, revoked, or expired refresh token"}},
        )
    _set_refresh_cookie(response, new_refresh, settings)
    return TokenResponse(access_token=access_token)


@router.post("/logout")
async def logout(
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
    body: LogoutRequest | None = Body(default=None),
) -> dict:
    body_token = body.refresh_token if body else None
    raw_refresh = request.cookies.get(REFRESH_COOKIE_NAME) or body_token
    # Clear on the *returned* object below (not just `response`) — an
    # explicitly-returned Response bypasses headers set on the injected
    # `response` dependency, and a raised HTTPException builds its own
    # response too, so a client always sheds the cookie either way.
    _clear_refresh_cookie(response, settings)
    if not raw_refresh:
        raise HTTPException(
            status_code=401,
            detail={"error": {"code": "INVALID_REFRESH_TOKEN", "message": "Invalid refresh token"}},
        )
    try:
        await auth_service.logout(session, raw_refresh)
    except ValueError:
        raise HTTPException(
            status_code=401,
            detail={"error": {"code": "INVALID_REFRESH_TOKEN", "message": "Invalid refresh token"}},
        )
    return {"message": "Logged out"}


@router.get("/me", response_model=UserResponse)
async def me(
    current_user: User = Depends(get_current_user_dep),
) -> UserResponse:
    # NEVER return password_hash
    return UserResponse.model_validate(current_user)


@router.post("/consent", response_model=UserResponse)
async def set_consent(
    body: ConsentRequest,
    current_user: User = Depends(get_current_user_dep),
    session: AsyncSession = Depends(get_db),
) -> UserResponse:
    """Grant or withdraw notification consent (P1.9, AccountPage toggle)."""
    user = await auth_service.set_consent(session, current_user, body.granted)
    return UserResponse.model_validate(user)


@router.delete("/me", status_code=204)
async def delete_me(
    body: DeleteAccountRequest,
    response: Response,
    current_user: User = Depends(get_current_user_dep),
    session: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
) -> Response:
    """Hard-delete the current user's account (P1.10, GDPR/PIPEDA)."""
    try:
        await auth_service.delete_account(session, current_user, body.password)
    except ValueError:
        raise HTTPException(
            status_code=403,
            detail={"error": {"code": "INVALID_PASSWORD", "message": "Incorrect password"}},
        )
    # Clear on the *returned* object (see logout's note above) — an
    # explicitly-built new Response would bypass headers set on the
    # injected `response` dependency.
    _clear_refresh_cookie(response, settings)
    response.status_code = 204
    return response


@router.get("/me/export")
async def export_me(
    current_user: User = Depends(get_current_user_dep),
    session: AsyncSession = Depends(get_db),
) -> dict:
    """Export the current user's data as JSON (P1.10, GDPR/PIPEDA)."""
    return await auth_service.export_account(session, current_user)
