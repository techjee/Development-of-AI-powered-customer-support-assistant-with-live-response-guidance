from contextlib import contextmanager
from typing import Iterator

from sqlalchemy.orm import Session

from database import SessionLocal


@contextmanager
def session_scope() -> Iterator[Session]:
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def commit_and_refresh(session: Session, instance):
    try:
        session.add(instance)
        session.commit()
        session.refresh(instance)
        return instance
    except Exception:
        session.rollback()
        raise


def commit_changes(session: Session):
    try:
        session.commit()
    except Exception:
        session.rollback()
        raise
