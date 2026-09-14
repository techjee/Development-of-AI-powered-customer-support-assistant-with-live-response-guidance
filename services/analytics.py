from datetime import datetime, timedelta, timezone

from sqlalchemy import case, func, or_, select
from sqlalchemy.orm import Session

from models import CaseEvent, Customer, Message, SupportCase, User


def total_cases(session: Session) -> int:
    return session.scalar(select(func.count(SupportCase.case_id))) or 0


def open_cases(session: Session) -> int:
    return session.scalar(
        select(func.count(SupportCase.case_id)).where(SupportCase.status != "RESOLVED")
    ) or 0


def resolved_cases(session: Session) -> int:
    return session.scalar(
        select(func.count(SupportCase.case_id)).where(SupportCase.status == "RESOLVED")
    ) or 0


def escalated_cases(session: Session) -> int:
    escalated_event = select(CaseEvent.event_id).where(
        CaseEvent.case_id == SupportCase.case_id,
        CaseEvent.event_type == "CASE_ESCALATED",
    ).exists()
    return session.scalar(
        select(func.count(SupportCase.case_id)).where(
            or_(
                SupportCase.ai_escalation.is_(True),
                SupportCase.escalation_status == "ESCALATED",
                escalated_event,
            )
        )
    ) or 0


def average_resolution_time(session: Session) -> float | None:
    value = session.scalar(
        select(func.avg(SupportCase.resolution_time)).where(
            SupportCase.resolution_time.is_not(None)
        )
    )
    return round(float(value), 2) if value is not None else None


def _grouped_case_counts(session: Session, column, label: str) -> list[dict]:
    value = func.coalesce(column, "Unspecified").label(label)
    rows = session.execute(
        select(value, func.count(SupportCase.case_id).label("count"))
        .group_by(value)
        .order_by(func.count(SupportCase.case_id).desc(), value)
    ).all()
    return [{label: item, "count": count} for item, count in rows]


def cases_by_department(session: Session) -> list[dict]:
    return _grouped_case_counts(session, SupportCase.department, "department")


def cases_by_sentiment(session: Session) -> list[dict]:
    return _grouped_case_counts(session, SupportCase.sentiment, "sentiment")


def cases_by_intent(session: Session) -> list[dict]:
    return _grouped_case_counts(session, SupportCase.intent, "intent")


def cases_by_urgency(session: Session) -> list[dict]:
    return _grouped_case_counts(session, SupportCase.urgency, "urgency")


def cases_by_escalation_risk(session: Session) -> list[dict]:
    return _grouped_case_counts(session, SupportCase.escalation_risk, "escalation_risk")


def agent_workload(session: Session) -> list[dict]:
    rows = session.execute(
        select(
            User.user_id,
            User.name,
            User.email,
            func.count(SupportCase.case_id).label("case_count"),
        )
        .join(SupportCase, SupportCase.assigned_agent_id == User.user_id)
        .where(User.role == "human_agent")
        .group_by(User.user_id, User.name, User.email)
        .order_by(func.count(SupportCase.case_id).desc(), User.name)
    ).all()
    return [
        {
            "user_id": user_id,
            "name": name,
            "email": email,
            "case_count": case_count,
        }
        for user_id, name, email, case_count in rows
    ]


def successfully_resolved_cases_per_agent(session: Session) -> list[dict]:
    rows = session.execute(
        select(
            User.user_id,
            User.name,
            User.email,
            func.count(SupportCase.case_id).label("resolved_count"),
        )
        .join(SupportCase, SupportCase.assigned_agent_id == User.user_id)
        .where(
            User.role == "human_agent",
            SupportCase.status == "RESOLVED",
            SupportCase.resolution_status.in_(["RESOLVED", "SUCCESS", "COMPLETED"]),
        )
        .group_by(User.user_id, User.name, User.email)
        .order_by(func.count(SupportCase.case_id).desc(), User.name)
    ).all()
    return [
        {
            "user_id": user_id,
            "name": name,
            "email": email,
            "resolved_count": resolved_count,
        }
        for user_id, name, email, resolved_count in rows
    ]


def agent_ranking(session: Session) -> list[dict]:
    resolved = func.sum(
        case(
            (
                (SupportCase.status == "RESOLVED")
                & SupportCase.resolution_status.in_(["RESOLVED", "SUCCESS", "COMPLETED"]),
                1,
            ),
            else_=0,
        )
    ).label("resolved_count")
    assigned = func.count(SupportCase.case_id).label("assigned_count")
    rows = session.execute(
        select(User.user_id, User.name, User.email, assigned, resolved)
        .join(SupportCase, SupportCase.assigned_agent_id == User.user_id, isouter=True)
        .where(User.role == "human_agent")
        .group_by(User.user_id, User.name, User.email)
        .order_by(resolved.desc(), assigned.desc(), User.name)
    ).all()
    ranking = []
    for rank, (user_id, name, email, assigned_count, resolved_count) in enumerate(rows, start=1):
        ranking.append(
            {
                "rank": rank,
                "user_id": user_id,
                "name": name,
                "email": email,
                "assigned_count": assigned_count or 0,
                "resolved_count": resolved_count or 0,
            }
        )
    return ranking


def ai_assisted_cases(session: Session) -> int:
    return session.scalar(
        select(func.count(SupportCase.case_id)).where(SupportCase.ai_assisted.is_(True))
    ) or 0


def ai_recommendations_used(session: Session) -> int:
    return session.scalar(
        select(func.count(SupportCase.case_id)).where(SupportCase.ai_recommendation_used.is_(True))
    ) or 0


def ai_recommendations_rejected(session: Session) -> int:
    return session.scalar(
        select(func.count(SupportCase.case_id)).where(SupportCase.ai_recommendation_rejected.is_(True))
    ) or 0


def ai_escalations(session: Session) -> int:
    return session.scalar(
        select(func.count(SupportCase.case_id)).where(SupportCase.ai_escalation.is_(True))
    ) or 0


def department_transfers(session: Session) -> int:
    return session.scalar(
        select(func.count(CaseEvent.event_id)).where(CaseEvent.event_type == "DEPARTMENT_TRANSFER")
    ) or 0


def customer_volume(session: Session) -> list[dict]:
    rows = session.execute(
        select(
            Customer.customer_id,
            Customer.name,
            func.count(SupportCase.case_id).label("case_count"),
        )
        .join(SupportCase, SupportCase.customer_id == Customer.customer_id)
        .group_by(Customer.customer_id, Customer.name)
        .order_by(func.count(SupportCase.case_id).desc(), Customer.customer_id)
    ).all()
    return [
        {"customer_id": customer_id, "name": name, "case_count": case_count}
        for customer_id, name, case_count in rows
    ]


def repeat_customers(session: Session) -> int:
    repeated = select(SupportCase.customer_id).group_by(SupportCase.customer_id).having(
        func.count(SupportCase.case_id) > 1
    ).subquery()
    return session.scalar(select(func.count()).select_from(repeated)) or 0


def agent_response_activity(session: Session) -> list[dict]:
    rows = session.execute(
        select(
            User.user_id,
            User.name,
            User.email,
            func.count(Message.message_id).label("response_count"),
        )
        .join(Message, Message.sender_id == User.user_id)
        .where(User.role == "human_agent", Message.sender_type == "human_agent")
        .group_by(User.user_id, User.name, User.email)
        .order_by(func.count(Message.message_id).desc(), User.name)
    ).all()
    return [
        {
            "user_id": user_id,
            "name": name,
            "email": email,
            "response_count": response_count,
        }
        for user_id, name, email, response_count in rows
    ]


def department_performance(session: Session) -> list[dict]:
    escalated_event = select(CaseEvent.event_id).where(
        CaseEvent.case_id == SupportCase.case_id,
        CaseEvent.event_type == "CASE_ESCALATED",
    ).exists()
    resolved_count = func.sum(
        case(
            (
                (SupportCase.status == "RESOLVED")
                & SupportCase.resolution_status.in_(["RESOLVED", "SUCCESS", "COMPLETED"]),
                1,
            ),
            else_=0,
        )
    )
    escalated_count = func.sum(
        case(
            (or_(SupportCase.escalation_status == "ESCALATED", SupportCase.ai_escalation.is_(True), escalated_event), 1),
            else_=0,
        )
    )
    department = func.coalesce(SupportCase.department, "Unspecified").label("department")
    rows = session.execute(
        select(department, resolved_count.label("resolved_count"), escalated_count.label("escalated_count"))
        .group_by(department)
        .order_by(department)
    ).all()
    return [
        {
            "department": name,
            "successfully_resolved": int(resolved or 0),
            "escalated": int(escalated or 0),
        }
        for name, resolved, escalated in rows
    ]


def agent_performance(session: Session) -> list[dict]:
    escalated_event = select(CaseEvent.event_id).where(
        CaseEvent.case_id == SupportCase.case_id,
        CaseEvent.event_type == "CASE_ESCALATED",
        CaseEvent.actor_id == User.user_id,
    ).exists()
    handled = func.count(SupportCase.case_id)
    resolved = func.sum(
        case(
            (
                (SupportCase.status == "RESOLVED")
                & SupportCase.resolution_status.in_(["RESOLVED", "SUCCESS", "COMPLETED"]),
                1,
            ),
            else_=0,
        )
    )
    average_time = func.avg(
        case(
            (SupportCase.resolution_time.is_not(None), SupportCase.resolution_time),
            else_=None,
        )
    )
    recommendations_used = func.sum(case((SupportCase.ai_recommendation_used.is_(True), 1), else_=0))
    recommendations_rejected = func.sum(case((SupportCase.ai_recommendation_rejected.is_(True), 1), else_=0))
    escalations = func.sum(case((or_(SupportCase.ai_escalation.is_(True), escalated_event), 1), else_=0))
    workload = func.sum(case((SupportCase.status != "RESOLVED", 1), else_=0))
    rows = session.execute(
        select(
            User.user_id,
            User.name,
            handled,
            resolved,
            workload,
            average_time,
            recommendations_used,
            recommendations_rejected,
            escalations,
        )
        .join(SupportCase, SupportCase.assigned_agent_id == User.user_id, isouter=True)
        .where(User.role == "human_agent")
        .group_by(User.user_id, User.name)
        .order_by(User.name)
    ).all()
    return [
        {
            "agent": name,
            "cases_handled": int(handled_count or 0),
            "cases_resolved": int(resolved_count or 0),
            "workload": int(workload_count or 0),
            "average_resolution_time_seconds": round(float(avg_seconds), 2) if avg_seconds is not None else None,
            "ai_recommendations_used": int(used or 0),
            "ai_recommendations_rejected": int(rejected or 0),
            "escalations": int(escalated or 0),
        }
        for (
            _user_id,
            name,
            handled_count,
            resolved_count,
            workload_count,
            avg_seconds,
            used,
            rejected,
            escalated,
        ) in rows
    ]


def complaint_trends(session: Session) -> list[str]:
    now = datetime.now(timezone.utc)
    last_day = now - timedelta(days=1)
    last_week = now - timedelta(days=7)
    last_month = now - timedelta(days=30)
    notifications = []

    def count_since(start, *, intent=None, department=None):
        statement = select(func.count(SupportCase.case_id)).where(SupportCase.created_at >= start)
        if intent:
            statement = statement.where(SupportCase.intent.ilike(f"%{intent}%"))
        if department:
            statement = statement.where(SupportCase.department.ilike(f"%{department}%"))
        return session.scalar(statement) or 0

    refund_day = count_since(last_day, intent="refund")
    refund_week = count_since(last_week, intent="refund")
    delivery_month = count_since(last_month, intent="delivery") + count_since(last_month, intent="shipping")
    if refund_day >= 3 and refund_day > max(1, refund_week // 7):
        notifications.append("Refund complaints are unusually high in the last 24 hours.")
    if delivery_month >= 3:
        notifications.append("Delivery-delay complaints are recurring over the last 30 days.")
    if not notifications:
        notifications.append("No significant complaint trends detected.")
    return notifications


def overall_summary(session: Session) -> dict:
    return {
        "total_cases": total_cases(session),
        "open_cases": open_cases(session),
        "resolved_cases": resolved_cases(session),
        "escalated_cases": escalated_cases(session),
        "average_resolution_time_seconds": average_resolution_time(session),
        "cases_by_department": cases_by_department(session),
        "department_performance": department_performance(session),
        "agent_performance": agent_performance(session),
        "complaint_trends": complaint_trends(session),
        "cases_by_sentiment": cases_by_sentiment(session),
        "cases_by_intent": cases_by_intent(session),
        "cases_by_urgency": cases_by_urgency(session),
        "cases_by_escalation_risk": cases_by_escalation_risk(session),
        "agent_workload": agent_workload(session),
        "successfully_resolved_cases_per_agent": successfully_resolved_cases_per_agent(session),
        "agent_ranking": agent_ranking(session),
        "ai_assisted_cases": ai_assisted_cases(session),
        "ai_recommendations_used": ai_recommendations_used(session),
        "ai_recommendations_rejected": ai_recommendations_rejected(session),
        "ai_escalations": ai_escalations(session),
        "department_transfers": department_transfers(session),
        "customer_volume": customer_volume(session),
        "repeat_customers": repeat_customers(session),
        "agent_response_activity": agent_response_activity(session),
    }
