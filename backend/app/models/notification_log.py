from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    String,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base, UTCDateTime

if TYPE_CHECKING:
    from app.models.subscription import Subscription


class PendingNotification(Base):
    __tablename__ = "pending_notifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    subscription_id: Mapped[str] = mapped_column(
        String, ForeignKey("subscriptions.id", ondelete="CASCADE"), nullable=False
    )
    ll2_id: Mapped[str] = mapped_column(String, nullable=False)
    change_type: Mapped[str] = mapped_column(String, nullable=False)
    old_value: Mapped[str | None] = mapped_column(String, nullable=True)
    new_value: Mapped[str | None] = mapped_column(String, nullable=True)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )

    subscription: Mapped[Subscription] = relationship("Subscription", lazy="raise")

    __table_args__ = (
        CheckConstraint(
            "change_type IN ('NET_SLIP','STATUS_CHANGE','NEW_LAUNCH')",
            name="ck_pending_notifications_change_type",
        ),
        Index(
            "ix_pending_notifications_attempts_created",
            "attempt_count",
            "created_at",
        ),
    )


class NotificationLog(Base):
    __tablename__ = "notification_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # P1.10: nullable — account deletion anonymizes these rows (user_id set
    # NULL) rather than deleting them, since they are billing/audit records.
    user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True
    )
    ll2_id: Mapped[str] = mapped_column(String, nullable=False)
    change_type: Mapped[str] = mapped_column(String, nullable=False)
    channel: Mapped[str] = mapped_column(String, nullable=False)
    delivery_status: Mapped[str] = mapped_column(String, nullable=False)
    error_detail: Mapped[str | None] = mapped_column(String, nullable=True)
    sent_at: Mapped[datetime] = mapped_column(
        UTCDateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )

    __table_args__ = (
        CheckConstraint("channel IN ('email','sms')", name="ck_notification_log_channel"),
        CheckConstraint(
            "delivery_status IN ('sent','failed')",
            name="ck_notification_log_delivery_status",
        ),
        Index("ix_notification_log_user_sent_at", "user_id", "sent_at"),
    )
