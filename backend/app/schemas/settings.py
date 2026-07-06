from __future__ import annotations

from pydantic import BaseModel


class SettingsStatus(BaseModel):
    nasa_key_set: bool
    n2yo_key_set: bool


class ApiKeyRequest(BaseModel):
    api_key: str
