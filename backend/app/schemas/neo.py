from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class NeoData(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    close_approach_date: str
    absolute_magnitude_h: float | None = None
    estimated_diameter_min_km: float | None = None
    estimated_diameter_max_km: float | None = None
    is_potentially_hazardous: bool
    relative_velocity_kph: float | None = None
    miss_distance_km: float | None = None
    orbiting_body: str | None = None
    nasa_jpl_url: str | None = None


class NeoFeedResponse(BaseModel):
    data: list[NeoData]
    cached: bool
    stale: bool = False
    fetched_at: datetime
    is_today: bool
