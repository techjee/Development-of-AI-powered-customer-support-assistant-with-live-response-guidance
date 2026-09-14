from sqlalchemy import select
from sqlalchemy.orm import Session

from models import User
from .sessions import commit_and_refresh


def create_user(
    session: Session,
    *,
    name: str,
    email: str,
    role: str,
    is_active: bool = True,
) -> User:
    return commit_and_refresh(
        session,
        User(name=name, email=email, role=role, is_active=is_active),
    )


def get_user_by_id(session: Session, user_id: int) -> User | None:
    return session.get(User, user_id)


def get_user_by_email(session: Session, email: str) -> User | None:
    return session.scalar(select(User).where(User.email == email))


def list_agents(session: Session, *, include_inactive: bool = False) -> list[User]:
    statement = select(User).where(User.role == "human_agent")
    if not include_inactive:
        statement = statement.where(User.is_active.is_(True))
    return list(session.scalars(statement.order_by(User.name, User.user_id)))
