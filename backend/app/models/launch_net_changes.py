from datetime import datetime

from sqlalchemy import CheckConstraint, ForeignKey, Index, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base, UTCDateTime


class LaunchNetChange(Base):
    __tablename__ = "launch_net_changes"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    launch_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("launches.ll2_id", ondelete="CASCADE"),
        nullable=False,
    )
    change_type: Mapped[str] = mapped_column(String, nullable=False)
    old_value: Mapped[str | None] = mapped_column(String, nullable=True)
    new_value: Mapped[str | None] = mapped_column(String, nullable=True)
    provider_name: Mapped[str] = mapped_column(String, nullable=False)
    rocket_name: Mapped[str] = mapped_column(String, nullable=False)
    pad_name: Mapped[str | None] = mapped_column(String, nullable=True)
    detected_at: Mapped[datetime] = mapped_column(
        UTCDateTime,
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )

    __table_args__ = (
        CheckConstraint(
            "change_type IN ('net', 'status', 'gone')",
            name="ck_launch_net_changes_change_type",
        ),
        Index("ix_launch_net_changes_launch_detected", "launch_id", "detected_at"),
        Index("ix_launch_net_changes_provider_detected", "provider_name", "detected_at"),
    )
