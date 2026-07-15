from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base, UTCDateTime


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    first_name: Mapped[str] = mapped_column(String, nullable=False)
    last_name: Mapped[str] = mapped_column(String, nullable=False)
    email: Mapped[str | None] = mapped_column(String, unique=True, nullable=True)
    phone: Mapped[str | None] = mapped_column(String, unique=True, nullable=True)
    password_hash: Mapped[str] = mapped_column(String, nullable=False)
    email_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    phone_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
    # P1.9: CASL/PIPEDA/GDPR — express consent to notification alerting.
    # consent_notifications_at is cleared back to null on withdrawal, which
    # is what subscription creation gates on (see subscription_service).
    consent_notifications_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    consent_source: Mapped[str | None] = mapped_column(String, nullable=True)
    # B1.1 (19-notification-channels-v2.md): per-user monthly SMS cap —
    # financial self-protection against SMS-pump abuse. sms_month is the
    # 'YYYY-MM' the counter applies to; the drain resets sms_sent_month to 0
    # whenever it sees a stale sms_month rather than running a separate
    # rollover job.
    sms_sent_month: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    sms_month: Mapped[str | None] = mapped_column(String, nullable=True)
    # L1 (20-location-and-sky-alerts.md) — sky-alert location, set via the
    # Open-Meteo geocoding proxy. lat/lng are rounded to 2 decimals at write
    # time (~1.1km precision) — plenty for pass/aurora visibility, and it
    # keeps pass_precompute's per-coordinate N2YO-call batching effective
    # across users in the same city instead of one call per exact address.
    location_name: Mapped[str | None] = mapped_column(String, nullable=True)
    location_lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    location_lng: Mapped[float | None] = mapped_column(Float, nullable=True)
    location_tz: Mapped[str | None] = mapped_column(String, nullable=True)
    # L1 — Pro flagship gating. No billing integration exists yet (see
    # BusinessPlan); status is granted via the admin-only
    # POST /api/v1/auth/admin/users/{id}/pro endpoint until a payment
    # provider is wired up.
    is_pro: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # L2 (19-notification-channels-v2.md) — capability-URL token for the
    # iCal feed. Generated on first rotate request, stored as a 32-byte
    # urlsafe random string. Null until the user requests a feed URL.
    # The token IS the auth for GET /api/v1/ical/{token}.ics — calendar
    # apps cannot send Bearer headers. Rotation invalidates the old URL.
    ical_token: Mapped[str | None] = mapped_column(String, unique=True, nullable=True)

    otps: Mapped[list["Otp"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    refresh_tokens: Mapped[list["RefreshToken"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )

    __table_args__ = (
        CheckConstraint(
            "email IS NOT NULL OR phone IS NOT NULL", name="ck_users_email_or_phone"
        ),
    )


class Otp(Base):
    __tablename__ = "otps"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    channel: Mapped[str] = mapped_column(String, nullable=False)
    code_hash: Mapped[str] = mapped_column(String, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    used: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    failed_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )

    user: Mapped["User"] = relationship(back_populates="otps")

    __table_args__ = (
        CheckConstraint("channel IN ('email','phone')", name="ck_otps_channel"),
        Index("ix_otps_user_channel_created", "user_id", "channel", "created_at"),
    )


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    token_hash: Mapped[str] = mapped_column(String, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    revoked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )

    user: Mapped["User"] = relationship(back_populates="refresh_tokens")

    __table_args__ = (
        Index("ix_refresh_tokens_token_hash", "token_hash"),
        Index("ix_refresh_tokens_user_revoked", "user_id", "revoked"),
    )


class LoginAttempt(Base):
    __tablename__ = "login_attempts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    identifier: Mapped[str] = mapped_column(String, nullable=False)
    ip_address: Mapped[str] = mapped_column(String, nullable=False)
    failed_at: Mapped[datetime] = mapped_column(
        UTCDateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )

    __table_args__ = (
        Index(
            "ix_login_attempts_identifier_ip_failed_at",
            "identifier",
            "ip_address",
            "failed_at",
        ),
    )
