from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from models import SupportCase, User
from .sessions import commit_and_refresh, commit_changes


_CASE_FIELDS = {
    "status",
    "resolved_at",
    "resolution_time",
    "first_response_at",
    "department",
    "intent",
    "sentiment",
    "urgency",
    "severity",
    "escalation_risk",
    "priority_label",
    "key_issue",
    "routing_reason",
    "resolution_status",
    "resolution_summary",
    "ai_assisted",
    "ai_recommendation_used",
    "ai_recommendation_rejected",
    "ai_escalation",
    "escalation_status",
    "escalation_reason",
    "escalated_at",
    "escalation_actor_id",
}


def create_case(
    session: Session,
    *,
    case_id: str,
    customer_id: str,
    assigned_agent_id: int | None = None,
    **fields,
) -> SupportCase:
    unknown_fields = set(fields) - _CASE_FIELDS
    if unknown_fields:
        raise ValueError(f"Unsupported case fields: {', '.join(sorted(unknown_fields))}")
    case = SupportCase(
        case_id=case_id,
        customer_id=customer_id,
        assigned_agent_id=assigned_agent_id,
        **fields,
    )
    return commit_and_refresh(session, case)


def get_case(session: Session, case_id: str) -> SupportCase | None:
    return session.get(SupportCase, case_id)


def list_cases(
    session: Session,
    *,
    status: str | None = None,
    customer_id: str | None = None,
    assigned_agent_id: int | None = None,
    department: str | None = None,
    escalation_risk: str | None = None,
    priority_label: str | None = None,
) -> list[SupportCase]:
    statement = select(SupportCase)
    filters = {
        SupportCase.status: status,
        SupportCase.customer_id: customer_id,
        SupportCase.assigned_agent_id: assigned_agent_id,
        SupportCase.department: department,
        SupportCase.escalation_risk: escalation_risk,
        SupportCase.priority_label: priority_label,
    }
    for column, value in filters.items():
        if value is not None:
            statement = statement.where(column == value)
    return list(session.scalars(statement.order_by(SupportCase.created_at, SupportCase.case_id)))


def update_case(session: Session, case_id: str, **changes) -> SupportCase | None:
    case = get_case(session, case_id)
    if case is None:
        return None
    unknown_fields = set(changes) - _CASE_FIELDS
    if unknown_fields:
        raise ValueError(f"Unsupported case fields: {', '.join(sorted(unknown_fields))}")
    for field, value in changes.items():
        setattr(case, field, value)
    commit_changes(session)
    session.refresh(case)
    return case


def assign_agent(session: Session, case_id: str, agent_id: int | None) -> SupportCase | None:
    case = get_case(session, case_id)
    if case is None:
        return None
    if agent_id is not None:
        agent = session.get(User, agent_id)
        if agent is None or agent.role != "human_agent" or not agent.is_active:
            raise ValueError("Agent must be an active Human Agent user.")
    case.assigned_agent_id = agent_id
    commit_changes(session)
    session.refresh(case)
    return case


def record_first_response(session: Session, case_id: str) -> SupportCase | None:
    case = get_case(session, case_id)
    if case is None:
        return None
    if case.first_response_at is None:
        case.first_response_at = datetime.now(timezone.utc)
        commit_changes(session)
        session.refresh(case)
    return case


def resolve_case(
    session: Session,
    case_id: str,
    *,
    resolution_summary: str | None = None,
) -> SupportCase | None:
    case = get_case(session, case_id)
    if case is None:
        return None
    if case.status == "RESOLVED":
        return case
    now = datetime.now(timezone.utc)
    created_at = case.created_at
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    case.status = "RESOLVED"
    case.resolution_status = "RESOLVED"
    case.resolution_summary = resolution_summary
    case.resolved_at = now
    case.resolution_time = max(0, int((now - created_at).total_seconds()))
    commit_changes(session)
    session.refresh(case)
    return case


def reopen_case(session: Session, case_id: str) -> SupportCase | None:
    case = get_case(session, case_id)
    if case is None:
        return None
    case.status = "NEW"
    case.resolution_status = "REOPENED"
    commit_changes(session)
    session.refresh(case)
    return case
