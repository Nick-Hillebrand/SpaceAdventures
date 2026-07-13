from __future__ import annotations

import secrets
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base, UTCDateTime

if TYPE_CHECKING:
    from app.models.user import User


class Subscription(Base):
    __tablename__ = "subscriptions"

    # Application-side default (not server_default): SQLite's
    # randomblob()/hex() functions have no Postgres equivalent, so the ID
    # is generated in Python to stay dialect-portable (16-postgres-migration.md P2.3).
    id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: secrets.token_hex(16)
    )
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    type: Mapped[str] = mapped_column(String, nullable=False)
    ll2_id: Mapped[str | None] = mapped_column(String, nullable=True)
    agency_name: Mapped[str | None] = mapped_column(String, nullable=True)
    notify_email: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    notify_sms: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )

    user: Mapped[User] = relationship("User", lazy="raise")

    __table_args__ = (
        CheckConstraint("type IN ('launch','agency')", name="ck_subscription_type"),
        UniqueConstraint("user_id", "type", "ll2_id", name="uq_subscription_launch"),
        UniqueConstraint("user_id", "type", "agency_name", name="uq_subscription_agency"),
        Index("ix_subscriptions_user_id", "user_id"),
        Index("ix_subscriptions_agency_name", "agency_name"),
    )
