from datetime import datetime

from sqlalchemy import DateTime, Integer, String, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class MarsPhoto(Base):
    __tablename__ = "mars_photo"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    sol: Mapped[int] = mapped_column(Integer, nullable=False)
    earth_date: Mapped[str] = mapped_column(String, nullable=False)
    rover_name: Mapped[str] = mapped_column(String, nullable=False)
    camera_name: Mapped[str] = mapped_column(String, nullable=False)
    img_src: Mapped[str] = mapped_column(String, nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )

    __table_args__ = (
        UniqueConstraint(
            "rover_name", "sol", "camera_name", "id", name="uq_mars_photo_composite"
        ),
    )
