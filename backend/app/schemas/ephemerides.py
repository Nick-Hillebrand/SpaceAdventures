from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class EphemerisPoint(BaseModel):
    t: datetime
    x: float
    y: float
    z: float


class EphemeridesResponse(BaseModel):
    slug: str
    name_key: str
    points: list[EphemerisPoint]
