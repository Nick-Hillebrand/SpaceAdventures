from __future__ import annotations

import secrets
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Index, Integer, String, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base, UTCDateTime

if TYPE_CHECKING:
    from app.models.user import User


class PushSubscription(Base):
    """A browser's Web Push endpoint (19-notification-channels-v2.md B1.2).

    One row per (user, browser/device) pair — `endpoint` is unique because
    that's what the browser's Push API issues per subscription; upserting on
    it is how re-subscribing the same browser doesn't duplicate rows.
    """

    __tablename__ = "push_subscriptions"

    id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: secrets.token_hex(16)
    )
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    endpoint: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    p256dh: Mapped[str] = mapped_column(String, nullable=False)
    auth: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )

    user: Mapped[User] = relationship("User", lazy="raise")

    __table_args__ = (Index("ix_push_subscriptions_user_id", "user_id"),)
