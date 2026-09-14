from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base


class SupportCase(Base):
    __tablename__ = "cases"
    __table_args__ = (
        Index("ix_cases_status", "status"),
        Index("ix_cases_department", "department"),
        Index("ix_cases_created_at", "created_at"),
        Index("ix_cases_updated_at", "updated_at"),
        Index("ix_cases_resolved_at", "resolved_at"),
        Index("ix_cases_escalation_risk", "escalation_risk"),
        Index("ix_cases_priority_label", "priority_label"),
    )

    case_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    customer_id: Mapped[str] = mapped_column(ForeignKey("customers.customer_id"), index=True, nullable=False)
    assigned_agent_id: Mapped[int | None] = mapped_column(ForeignKey("users.user_id"), index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="NEW")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    first_response_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolution_time: Mapped[int | None] = mapped_column(Integer)
    department: Mapped[str | None] = mapped_column(String(100))
    intent: Mapped[str | None] = mapped_column(String(200))
    sentiment: Mapped[str | None] = mapped_column(String(64))
    urgency: Mapped[str | None] = mapped_column(String(32))
    severity: Mapped[str | None] = mapped_column(String(32))
    escalation_risk: Mapped[str | None] = mapped_column(String(32))
    priority_label: Mapped[str | None] = mapped_column(String(32))
    key_issue: Mapped[str | None] = mapped_column(Text)
    routing_reason: Mapped[str | None] = mapped_column(Text)
    resolution_status: Mapped[str | None] = mapped_column(String(32))
    resolution_summary: Mapped[str | None] = mapped_column(Text)
    ai_assisted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    ai_recommendation_used: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    ai_recommendation_rejected: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    ai_escalation: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    escalation_status: Mapped[str | None] = mapped_column(String(32))
    escalation_reason: Mapped[str | None] = mapped_column(Text)
    escalated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    escalation_actor_id: Mapped[int | None] = mapped_column(ForeignKey("users.user_id"), index=True)

    customer = relationship("Customer", back_populates="cases")
    assigned_agent = relationship(
        "User",
        back_populates="assigned_cases",
        foreign_keys=[assigned_agent_id],
    )
    messages = relationship("Message", back_populates="case", cascade="all, delete-orphan")
    events = relationship("CaseEvent", back_populates="case", cascade="all, delete-orphan")