from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


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


class LaunchesResponse(BaseModel):
    data: list[LaunchOut]
    last_synced_at: datetime | None
    cached: bool = True
