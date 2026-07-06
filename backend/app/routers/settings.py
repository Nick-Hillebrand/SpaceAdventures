from __future__ import annotations

from fastapi import APIRouter, Request

from app.schemas.settings import ApiKeyRequest, SettingsStatus

router = APIRouter(prefix="/api/v1/settings", tags=["settings"])


@router.get("", response_model=SettingsStatus)
async def get_settings(request: Request) -> SettingsStatus:
    s = request.app.state.settings
    return SettingsStatus(
        nasa_key_set=bool(s.nasa_api_key),
        n2yo_key_set=bool(s.n2yo_api_key),
    )


@router.post("/nasa-api-key")
async def set_nasa_api_key(body: ApiKeyRequest, request: Request) -> dict[str, str]:
    request.app.state.settings.nasa_api_key = body.api_key
    return {"message": "NASA API key updated"}


@router.post("/n2yo-api-key")
async def set_n2yo_api_key(body: ApiKeyRequest, request: Request) -> dict[str, str]:
    request.app.state.settings.n2yo_api_key = body.api_key
    return {"message": "N2YO API key updated"}
