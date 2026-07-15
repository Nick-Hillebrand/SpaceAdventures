from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
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
    # L1: nullable — a change_type='ISS_PASS' row carries iss_pass_alert_id
    # instead. Exactly one of the two is set, enforced in
    # iss_pass_alert_service/notification_service rather than a CHECK, to
    # match the existing launch-shaped code path (which never validates this
    # either).
    ll2_id: Mapped[str | None] = mapped_column(String, nullable=True)
    iss_pass_alert_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("iss_pass_alerts.id", ondelete="CASCADE"), nullable=True
    )
    change_type: Mapped[str] = mapped_column(String, nullable=False)
    old_value: Mapped[str | None] = mapped_column(String, nullable=True)
    new_value: Mapped[str | None] = mapped_column(String, nullable=True)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # B1.1 (19-notification-channels-v2.md): drain reschedules a failed row
    # instead of retrying immediately — next_attempt_at holds it back until
    # the backoff window elapses. dead=TRUE after 5 attempts; the row stays
    # (visible in the admin health dead-letter count) instead of being purged,
    # so an operator can see the queue actually stalled rather than silently
    # losing rows.
    next_attempt_at: Mapped[datetime] = mapped_column(
        UTCDateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
    dead: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )

    subscription: Mapped[Subscription] = relationship("Subscription", lazy="raise")

    __table_args__ = (
        CheckConstraint(
            "change_type IN ('NET_SLIP','STATUS_CHANGE','NEW_LAUNCH','ISS_PASS')",
            name="ck_pending_notifications_change_type",
        ),
        Index(
            "ix_pending_notifications_attempts_created",
            "attempt_count",
            "created_at",
        ),
        Index(
            "ix_pending_notifications_dead_next_attempt",
            "dead",
            "next_attempt_at",
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
    ll2_id: Mapped[str | None] = mapped_column(String, nullable=True)
    # L1: SET NULL (not CASCADE) — a future pass-cleanup job deleting old
    # iss_pass_alerts rows must never destroy this billing/audit record, the
    # same reasoning as user_id above.
    iss_pass_alert_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("iss_pass_alerts.id", ondelete="SET NULL"), nullable=True
    )
    change_type: Mapped[str] = mapped_column(String, nullable=False)
    channel: Mapped[str] = mapped_column(String, nullable=False)
    delivery_status: Mapped[str] = mapped_column(String, nullable=False)
    error_detail: Mapped[str | None] = mapped_column(String, nullable=True)
    sent_at: Mapped[datetime] = mapped_column(
        UTCDateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )

    __table_args__ = (
        CheckConstraint("channel IN ('email','sms','push')", name="ck_notification_log_channel"),
        CheckConstraint(
            "delivery_status IN ('sent','failed')",
            name="ck_notification_log_delivery_status",
        ),
        Index("ix_notification_log_user_sent_at", "user_id", "sent_at"),
    )
