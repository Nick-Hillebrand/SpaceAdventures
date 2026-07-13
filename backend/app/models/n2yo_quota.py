from datetime import datetime

from sqlalchemy import Integer
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base, UTCDateTime


class N2yoQuota(Base):
    __tablename__ = "n2yo_quota"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    window_start: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    used: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
