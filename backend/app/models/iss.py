from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Float, Integer, String, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class IssPositionBatch(Base):
    __tablename__ = "iss_position_batch"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    positions: Mapped[str] = mapped_column(String, nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )


class IssTle(Base):
    __tablename__ = "iss_tle"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    tle_line0: Mapped[str] = mapped_column(String, nullable=False)
    tle_line1: Mapped[str] = mapped_column(String, nullable=False)
    tle_line2: Mapped[str] = mapped_column(String, nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )


class IssPassSet(Base):
    __tablename__ = "iss_passes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    pass_type: Mapped[str] = mapped_column(String, nullable=False)
    observer_lat: Mapped[float] = mapped_column(Float, nullable=False)
    observer_lng: Mapped[float] = mapped_column(Float, nullable=False)
    observer_alt: Mapped[float] = mapped_column(Float, nullable=False)
    passes_json: Mapped[str] = mapped_column(String, nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )

    __table_args__ = (
        CheckConstraint("pass_type IN ('visual','radio')", name="ck_iss_pass_type"),
        UniqueConstraint(
            "pass_type", "observer_lat", "observer_lng", "observer_alt", name="uq_iss_passes"
        ),
    )
