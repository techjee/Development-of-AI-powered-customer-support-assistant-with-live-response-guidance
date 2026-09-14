import os
from typing import Generator

from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


load_dotenv(override=True)

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is not set in the environment or .env file.")


class Base(DeclarativeBase):
    pass


engine = create_engine(
    DATABASE_URL,
    connect_args={"sslmode": "require"},
    pool_pre_ping=True,
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def ensure_auth_schema() -> None:
    """Add columns introduced by staged features to existing databases."""
    with engine.begin() as connection:
        connection.execute(
            text("ALTER TABLE users ADD COLUMN IF NOT EXISTS password_hash VARCHAR(255)")
        )
        connection.execute(
            text("ALTER TABLE cases ADD COLUMN IF NOT EXISTS routing_reason TEXT")
        )
        connection.execute(
            text("ALTER TABLE cases ADD COLUMN IF NOT EXISTS escalation_status VARCHAR(32)")
        )
        connection.execute(
            text("ALTER TABLE cases ADD COLUMN IF NOT EXISTS escalation_reason TEXT")
        )
        connection.execute(
            text("ALTER TABLE cases ADD COLUMN IF NOT EXISTS escalated_at TIMESTAMPTZ")
        )
        connection.execute(
            text("ALTER TABLE cases ADD COLUMN IF NOT EXISTS escalation_actor_id INTEGER")
        )


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def test_connection() -> int:
    with engine.connect() as connection:
        return connection.execute(text("SELECT 1")).scalar_one()


if __name__ == "__main__":
    result = test_connection()
    print(f"Neon database connection successful: SELECT 1 returned {result}")