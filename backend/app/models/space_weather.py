from datetime import datetime

from sqlalchemy import JSON, CheckConstraint, Index, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base, UTCDateTime


class SpaceWeatherEvent(Base):
    __tablename__ = "space_weather_event"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    event_type: Mapped[str] = mapped_column(String, nullable=False)
    start_date: Mapped[str] = mapped_column(String, nullable=False)
    raw_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(
        UTCDateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )

    __table_args__ = (
        CheckConstraint(
            "event_type IN ('FLR','GST','RBE','SEP','CME')",
            name="ck_space_weather_event_type",
        ),
        Index("ix_space_weather_event_type_start_date", "event_type", "start_date"),
    )
