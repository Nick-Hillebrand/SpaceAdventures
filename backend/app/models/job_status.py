from datetime import datetime

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base, UTCDateTime


class JobStatus(Base):
    """Heartbeat row per registered job (17-worker-and-scheduling.md P3.5).

    `last_error` is always run through `notification_service.scrub_error`
    before being written — this table is readable via the admin health
    endpoint and must never leak secrets.
    """

    __tablename__ = "job_status"

    job_name: Mapped[str] = mapped_column(String, primary_key=True)
    last_success_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    last_error: Mapped[str | None] = mapped_column(String, nullable=True)
