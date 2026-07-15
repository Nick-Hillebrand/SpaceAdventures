"""Pydantic schemas for sky-location endpoints (20-location-and-sky-alerts.md)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class LocationCandidate(BaseModel):
    name: str
    country: str | None = None
    admin1: str | None = None
    latitude: float
    longitude: float
    timezone: str


class LocationSearchResponse(BaseModel):
    candidates: list[LocationCandidate]


class SetLocationRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    latitude: float
    longitude: float
    timezone: str = Field(min_length=1, max_length=100)


class LocationOut(BaseModel):
    location_name: str | None
    location_lat: float | None
    location_lng: float | None
    location_tz: str | None

    model_config = ConfigDict(from_attributes=True)
