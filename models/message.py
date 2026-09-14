from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base


class Message(Base):
    __tablename__ = "messages"
    __table_args__ = (
        Index("ix_messages_case_id", "case_id"),
        Index("ix_messages_timestamp", "timestamp"),
    )

    message_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.case_id"), nullable=False)
    sender_type: Mapped[str] = mapped_column(String(32), nullable=False)
    sender_id: Mapped[int | None] = mapped_column(ForeignKey("users.user_id"))
    message: Mapped[str] = mapped_column(Text, nullable=False)
    language: Mapped[str | None] = mapped_column(String(32))
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

    case = relationship("SupportCase", back_populates="messages")
    sender = relationship("User", back_populates="messages")