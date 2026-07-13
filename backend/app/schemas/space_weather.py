from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class SpaceWeatherEventData(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    event_type: str
    start_date: str
    raw_json: dict


class SpaceWeatherResponse(BaseModel):
    data: list[SpaceWeatherEventData]
    cached: bool
    stale: bool = False
    fetched_at: datetime
    is_today: bool
