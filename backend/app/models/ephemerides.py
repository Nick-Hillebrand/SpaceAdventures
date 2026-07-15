from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base, UTCDateTime


class TrackedObject(Base):
    __tablename__ = "tracked_objects"

    spk_id: Mapped[str] = mapped_column(String, primary_key=True)
    slug: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    name_key: Mapped[str] = mapped_column(String, nullable=False)
    kind: Mapped[str] = mapped_column(String, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    step_hours: Mapped[int] = mapped_column(Integer, nullable=False, default=24)

    __table_args__ = (
        CheckConstraint(
            "kind IN ('spacecraft', 'small_body')", name="ck_tracked_objects_kind"
        ),
    )


class Ephemeris(Base):
    __tablename__ = "ephemerides"

    spk_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("tracked_objects.spk_id", ondelete="CASCADE"),
        primary_key=True,
    )
    t_utc: Mapped[datetime] = mapped_column(UTCDateTime, primary_key=True)
    x_au: Mapped[float] = mapped_column(Float, nullable=False)
    y_au: Mapped[float] = mapped_column(Float, nullable=False)
    z_au: Mapped[float] = mapped_column(Float, nullable=False)
