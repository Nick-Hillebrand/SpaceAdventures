from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class IssPositionsResponse(BaseModel):
    positions: list[dict]
    fetched_at: datetime
    cached: bool
    quota_exhausted: bool = False


class IssTleResponse(BaseModel):
    tle_line0: str
    tle_line1: str
    tle_line2: str
    fetched_at: datetime
    cached: bool
    quota_exhausted: bool = False


class IssPassesResponse(BaseModel):
    passes: list[dict]
    fetched_at: datetime
    cached: bool
    quota_exhausted: bool = False


class IssQuotaResponse(BaseModel):
    used: int
    cap: int
    window_start: datetime
    resets_at: datetime
