from __future__ import annotations

import json
from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator


class LivestreamUrl(BaseModel):
    title: str
    url: str
    feature_image: str = ""


class LaunchOut(BaseModel):
    ll2_id: str
    name: str
    net: datetime
    status_abbrev: str
    status_name: str
    agency_name: str
    agency_type: str | None
    rocket_name: str
    rocket_family: str | None
    mission_name: str | None
    mission_description: str | None
    mission_type: str | None
    pad_name: str
    pad_location: str
    image_url: str | None
    livestream_urls: list[LivestreamUrl]
    fetched_at: datetime

    model_config = ConfigDict(from_attributes=True)

    @field_validator("livestream_urls", mode="before")
    @classmethod
    def _parse_livestream(cls, v: object) -> object:
        if isinstance(v, str):
            return json.loads(v)
        return v


class LaunchesResponse(BaseModel):
    data: list[LaunchOut]
    last_synced_at: datetime | None
    cached: bool = True
