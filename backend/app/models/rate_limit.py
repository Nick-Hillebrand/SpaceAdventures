from datetime import datetime

from sqlalchemy import Index, Integer, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base, UTCDateTime


class RateLimitEvent(Base):
    __tablename__ = "rate_limit_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    bucket: Mapped[str] = mapped_column(String, nullable=False)
    ip_hash: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )

    __table_args__ = (
        Index("ix_rate_limit_events_bucket_ip_created", "bucket", "ip_hash", "created_at"),
    )
