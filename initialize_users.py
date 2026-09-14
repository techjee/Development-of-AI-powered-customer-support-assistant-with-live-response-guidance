"""Initialize or update database-backed demo users using environment passwords."""

import os

from dotenv import load_dotenv

from database import SessionLocal, ensure_auth_schema
from models import User
from services.auth import hash_password


def upsert_user(session, *, email: str, name: str, role: str, password: str) -> None:
    user = session.query(User).filter(User.email == email).one_or_none()
    if user is None:
        user = User(email=email, name=name, role=role)
        session.add(user)
    user.name = name
    user.role = role
    user.is_active = True
    user.password_hash = hash_password(password)


def main() -> None:
    load_dotenv(override=True)
    ensure_auth_schema()
    admin_email = os.getenv("ADMIN_USERNAME")
    admin_password = os.getenv("ADMIN_INITIAL_PASSWORD")
    agent_email = os.getenv("AGENT_USERNAME")
    agent_password = os.getenv("AGENT_INITIAL_PASSWORD")
    if not all((admin_email, admin_password, agent_email, agent_password)):
        raise RuntimeError(
            "Set ADMIN_USERNAME, ADMIN_INITIAL_PASSWORD, AGENT_USERNAME, "
            "and AGENT_INITIAL_PASSWORD before running this command."
        )

    with SessionLocal() as session:
        upsert_user(
            session,
            email=admin_email.strip().lower(),
            name=os.getenv("ADMIN_DISPLAY_NAME", "Administrator"),
            role="admin",
            password=admin_password,
        )
        upsert_user(
            session,
            email=agent_email.strip().lower(),
            name=os.getenv("AGENT_DISPLAY_NAME", "Human Agent"),
            role="human_agent",
            password=agent_password,
        )
        session.commit()
    print("Database users initialized with hashed passwords.")


if __name__ == "__main__":
    main()