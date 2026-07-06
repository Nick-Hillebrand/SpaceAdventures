from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class MarsPhotoData(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    sol: int
    earth_date: str
    rover_name: str
    camera_name: str
    img_src: str


class MarsPhotosResponse(BaseModel):
    data: list[MarsPhotoData]
    cached: bool
    stale: bool = False
    fetched_at: datetime
    is_today: bool


class RoverInfo(BaseModel):
    name: str
    cameras: list[str]


class RoversResponse(BaseModel):
    data: list[RoverInfo]
