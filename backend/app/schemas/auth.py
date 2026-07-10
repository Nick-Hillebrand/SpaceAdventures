"""Pydantic schemas for authentication endpoints."""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class RegisterRequest(BaseModel):
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    email: str | None = Field(default=None, max_length=254)
    phone: str | None = Field(default=None, max_length=32)
    password: str

    @field_validator("email")
    @classmethod
    def email_shape(cls, v: str | None) -> str | None:
        if v is not None and v != "" and ("@" not in v or v.count("@") != 1):
            raise ValueError("Invalid email address")
        return v

    @field_validator("password")
    @classmethod
    def password_length(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        # bcrypt silently truncates beyond 72 bytes — reject instead
        if len(v.encode("utf-8")) > 72:
            raise ValueError("Password must be at most 72 bytes")
        return v


class VerifyOtpRequest(BaseModel):
    otp: str


class ResendOtpRequest(BaseModel):
    channel: Literal["email", "phone"]


class LoginRequest(BaseModel):
    email_or_phone: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str


class RefreshRequest(BaseModel):
    refresh_token: str


class LogoutRequest(BaseModel):
    refresh_token: str


class UserResponse(BaseModel):
    id: int
    first_name: str
    last_name: str
    email: str | None
    phone: str | None
    email_verified: bool
    phone_verified: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
