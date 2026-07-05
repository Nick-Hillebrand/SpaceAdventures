from datetime import datetime

from sqlalchemy import DateTime, Index, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Launch(Base):
    __tablename__ = "launches"

    ll2_id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    net: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    status_abbrev: Mapped[str] = mapped_column(String, nullable=False)
    status_name: Mapped[str] = mapped_column(String, nullable=False)
    agency_name: Mapped[str] = mapped_column(String, nullable=False)
    agency_type: Mapped[str | None] = mapped_column(String, nullable=True)
    rocket_name: Mapped[str] = mapped_column(String, nullable=False)
    rocket_family: Mapped[str | None] = mapped_column(String, nullable=True)
    mission_name: Mapped[str | None] = mapped_column(String, nullable=True)
    mission_description: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    mission_type: Mapped[str | None] = mapped_column(String, nullable=True)
    pad_name: Mapped[str] = mapped_column(String, nullable=False)
    pad_location: Mapped[str] = mapped_column(String, nullable=False)
    image_url: Mapped[str | None] = mapped_column(String, nullable=True)
    livestream_urls: Mapped[str] = mapped_column(String, nullable=False, default="[]")
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )

    __table_args__ = (
        Index("ix_launches_net", "net"),
        Index("ix_launches_agency_name", "agency_name"),
    )
