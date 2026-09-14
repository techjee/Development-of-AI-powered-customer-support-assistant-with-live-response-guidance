from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from models import CaseEvent
from .sessions import commit_and_refresh


def create_case_event(
    session: Session,
    *,
    case_id: str,
    actor_type: str,
    event_type: str,
    actor_id: int | None = None,
    event_details: dict | None = None,
    timestamp: datetime | None = None,
) -> CaseEvent:
    return commit_and_refresh(
        session,
        CaseEvent(
            case_id=case_id,
            actor_type=actor_type,
            actor_id=actor_id,
            event_type=event_type,
            event_details=event_details,
            timestamp=timestamp,
        ),
    )


def create_case_event_once(
    session: Session,
    *,
    case_id: str,
    actor_type: str,
    event_type: str,
    actor_id: int | None = None,
    event_details: dict | None = None,
    timestamp: datetime | None = None,
) -> CaseEvent:
    statement = select(CaseEvent).where(
        CaseEvent.case_id == case_id,
        CaseEvent.actor_type == actor_type,
        CaseEvent.actor_id == actor_id,
        CaseEvent.event_type == event_type,
    )
    existing_events = session.scalars(statement).all()
    for existing in existing_events:
        if existing.event_details == event_details:
            return existing
    return create_case_event(
        session,
        case_id=case_id,
        actor_type=actor_type,
        actor_id=actor_id,
        event_type=event_type,
        event_details=event_details,
        timestamp=timestamp,
    )


def get_case_events(
    session: Session,
    case_id: str,
    *,
    event_type: str | None = None,
) -> list[CaseEvent]:
    statement = select(CaseEvent).where(CaseEvent.case_id == case_id)
    if event_type is not None:
        statement = statement.where(CaseEvent.event_type == event_type)
    statement = statement.order_by(CaseEvent.timestamp, CaseEvent.event_id)
    return list(session.scalars(statement))
