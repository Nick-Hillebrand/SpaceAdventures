from datetime import datetime

from sqlalchemy import Boolean, Float, ForeignKey, Index, Integer, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base, UTCDateTime


class IssPassAlert(Base):
    """One precomputed ISS visual pass for one user's sky location
    (20-location-and-sky-alerts.md L1).

    Named `iss_pass_alerts` rather than the spec's literal `iss_passes` —
    that name is already taken by the pre-existing generic public-observer
    pass cache (`IssPassSet`, keyed by (pass_type, lat, lng, alt), used by
    GET /api/v1/iss/passes/{visual,radio}). This table is a different shape
    entirely: one row per (user, pass), carrying the `notified` flag
    pass_notify uses to avoid double-alerting.
    """

    __tablename__ = "iss_pass_alerts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    start_utc: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    end_utc: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    max_el: Mapped[float] = mapped_column(Float, nullable=False)
    start_az: Mapped[float] = mapped_column(Float, nullable=False)
    end_az: Mapped[float] = mapped_column(Float, nullable=False)
    mag: Mapped[float | None] = mapped_column(Float, nullable=True)
    notified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    fetched_at: Mapped[datetime] = mapped_column(
        UTCDateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )

    __table_args__ = (
        UniqueConstraint("user_id", "start_utc", name="uq_iss_pass_alerts_user_start"),
        Index("ix_iss_pass_alerts_notified_start", "notified", "start_utc"),
    )
