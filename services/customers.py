from sqlalchemy import select
from sqlalchemy.orm import Session

from models import Customer
from .sessions import commit_and_refresh, commit_changes


_CUSTOMER_FIELDS = {"name", "email", "language", "customer_tier"}


def create_customer(
    session: Session,
    *,
    customer_id: str,
    name: str,
    email: str | None = None,
    language: str | None = None,
    customer_tier: str | None = None,
) -> Customer:
    return commit_and_refresh(
        session,
        Customer(
            customer_id=customer_id,
            name=name,
            email=email,
            language=language,
            customer_tier=customer_tier,
        ),
    )


def get_customer_by_id(session: Session, customer_id: str) -> Customer | None:
    return session.get(Customer, customer_id)


def get_customer_by_email(session: Session, email: str) -> Customer | None:
    return session.scalar(select(Customer).where(Customer.email == email))


def update_customer(session: Session, customer_id: str, **changes) -> Customer | None:
    customer = get_customer_by_id(session, customer_id)
    if customer is None:
        return None
    unknown_fields = set(changes) - _CUSTOMER_FIELDS
    if unknown_fields:
        raise ValueError(f"Unsupported customer fields: {', '.join(sorted(unknown_fields))}")
    for field, value in changes.items():
        setattr(customer, field, value)
    commit_changes(session)
    session.refresh(customer)
    return customer
