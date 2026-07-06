"""Pydantic schemas for subscription endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict


class CreateSubscriptionRequest(BaseModel):
    type: Literal["launch", "agency"]
    ll2_id: str | None = None
    agency_name: str | None = None
    notify_email: bool = False
    notify_sms: bool = False


class SubscriptionOut(BaseModel):
    id: str
    type: str
    ll2_id: str | None
    agency_name: str | None
    notify_email: bool
    notify_sms: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class UnsubscribeRequest(BaseModel):
    token: str
