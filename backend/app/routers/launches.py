from __future__ import annotations

import secrets
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
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


def _get_translator(request: Request) -> Any:
    return getattr(request.app.state, "translator", None)


def _require_admin(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> None:
    settings = request.app.state.settings
    if not settings.admin_api_key:
        raise HTTPException(status_code=503, detail="Admin API key not configured")
    expected = f"Bearer {settings.admin_api_key}"
    auth_header = request.headers.get("Authorization", "")
    # Constant-time comparison — a plain != leaks key prefixes via timing.
    if not secrets.compare_digest(auth_header.encode(), expected.encode()):
        raise HTTPException(status_code=401, detail="Unauthorized")


def _apply_launch_translations(launch: LaunchOut, translations: dict | None, lang: str) -> LaunchOut:
    if lang == "en" or not translations:
        return launch
    lang_data = translations.get(lang, {})
    if not lang_data:
        return launch
    updates: dict[str, Any] = {}
    if "mission_name" in lang_data and lang_data["mission_name"]:
        updates["mission_name"] = lang_data["mission_name"]
    if "mission_description" in lang_data and lang_data["mission_description"]:
        updates["mission_description"] = lang_data["mission_description"]
    if not updates:
        return launch
    return launch.model_copy(update=updates)


@router.get("/upcoming", response_model=LaunchesResponse)
async def get_upcoming_launches(
    lang: str = Query(default="en", description="ISO 639-1 language code"),
    session: AsyncSession = Depends(get_db),
) -> LaunchesResponse:
    launches, last_synced_at = await launches_service.get_upcoming_launches(session)
    result: list[LaunchOut] = []
    for launch in launches:
        out = LaunchOut.model_validate(launch)
        out = _apply_launch_translations(out, launch.translations_json, lang)
        result.append(out)
    return LaunchesResponse(
        data=result,
        last_synced_at=last_synced_at,
        cached=True,
    )


@router.post("/sync", status_code=200)
async def sync_launches(
    session: AsyncSession = Depends(get_db),
    ll2_client: LL2Client = Depends(_get_ll2_client),
    translator: Any = Depends(_get_translator),
    _admin: None = Depends(_require_admin),
) -> dict[str, str]:
    await launches_service.sync_launches(session, ll2_client, translator=translator)
    return {"status": "ok"}
