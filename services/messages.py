from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from models import Message
from .sessions import commit_and_refresh


def add_message(
    session: Session,
    *,
    case_id: str,
    sender_type: str,
    message: str,
    sender_id: int | None = None,
    language: str | None = None,
    timestamp: datetime | None = None,
) -> Message:
    return commit_and_refresh(
        session,
        Message(
            case_id=case_id,
            sender_type=sender_type,
            sender_id=sender_id,
            message=message,
            language=language,
            timestamp=timestamp,
        ),
    )


def get_case_messages(session: Session, case_id: str) -> list[Message]:
    statement = select(Message).where(Message.case_id == case_id).order_by(Message.timestamp, Message.message_id)
    return list(session.scalars(statement))


def get_existing_message(
    session: Session,
    *,
    case_id: str,
    sender_type: str,
    message: str,
    sender_id: int | None = None,
) -> Message | None:
    statement = select(Message).where(
        Message.case_id == case_id,
        Message.sender_type == sender_type,
        Message.sender_id == sender_id,
        Message.message == message,
    )
    return session.scalar(statement)
