from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, Index, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Neo(Base):
    __tablename__ = "neo"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    close_approach_date: Mapped[str] = mapped_column(String, nullable=False)
    absolute_magnitude_h: Mapped[float | None] = mapped_column(Float, nullable=True)
    estimated_diameter_min_km: Mapped[float | None] = mapped_column(Float, nullable=True)
    estimated_diameter_max_km: Mapped[float | None] = mapped_column(Float, nullable=True)
    is_potentially_hazardous: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    relative_velocity_kph: Mapped[float | None] = mapped_column(Float, nullable=True)
    miss_distance_km: Mapped[float | None] = mapped_column(Float, nullable=True)
    orbiting_body: Mapped[str | None] = mapped_column(String, nullable=True)
    nasa_jpl_url: Mapped[str | None] = mapped_column(String, nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )

    __table_args__ = (Index("ix_neo_close_approach_date", "close_approach_date"),)
