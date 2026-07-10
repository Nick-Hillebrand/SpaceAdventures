from __future__ import annotations

from fastapi import APIRouter, Request

from app.schemas.settings import SettingsStatus

router = APIRouter(prefix="/api/v1/settings", tags=["settings"])

# API keys are server configuration, provided exclusively via environment
# variables. The former POST endpoints that mutated them at runtime were an
# unauthenticated write to process-global state and have been removed.


@router.get("", response_model=SettingsStatus)
async def get_settings(request: Request) -> SettingsStatus:
    s = request.app.state.settings
    return SettingsStatus(
        nasa_key_set=bool(s.nasa_api_key),
        n2yo_key_set=bool(s.n2yo_api_key),
    )
