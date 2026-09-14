from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base


class CaseEvent(Base):
    __tablename__ = "case_events"
    __table_args__ = (
        Index("ix_case_events_case_id", "case_id"),
        Index("ix_case_events_event_type", "event_type"),
        Index("ix_case_events_timestamp", "timestamp"),
    )

    event_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.case_id"), nullable=False)
    actor_type: Mapped[str] = mapped_column(String(32), nullable=False)
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("users.user_id"))
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    event_details: Mapped[dict | None] = mapped_column(JSON)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

    case = relationship("SupportCase", back_populates="events")
    actor = relationship("User", back_populates="events")