from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ApodData(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    date: str
    title: str
    explanation: str
    url: str
    hdurl: str | None = None
    media_type: str
    copyright: str | None = None
    thumbnail_url: str | None = None


class ApodResponse(BaseModel):
    data: ApodData
    cached: bool
    stale: bool = False
    fetched_at: datetime
    is_today: bool
