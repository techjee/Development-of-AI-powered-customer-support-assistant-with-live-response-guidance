from sqlalchemy.orm import Session

from models import SupportCase
from .case_events import get_case_events
from .messages import get_case_messages


ANALYSIS_FIELDS = {
    "intent": "customer_intent",
    "sentiment": "sentiment",
    "urgency": "urgency",
    "escalation_risk": "escalation_risk",
    "key_issue": "key_issue",
    "conversation_context": "conversation_context",
    "recommended_next_action": "recommended_next_step",
    "related_policy": "related_policy",
}


def get_stored_case_analysis(
    session: Session,
    *,
    customer_id: str,
    case_id: str,
    include_messages: bool = True,
) -> dict | None:
    case = session.get(SupportCase, case_id)
    if case is None or case.customer_id != customer_id:
        return None

    analysis_events = get_case_events(session, case_id, event_type="AI_ANALYSIS")
    analysis_event = analysis_events[-1] if analysis_events else None
    stored_analysis = (
        (analysis_event.event_details or {}).get("analysis", {})
        if analysis_event
        else {}
    )

    analysis = {
        field: stored_analysis.get(event_key)
        for field, event_key in ANALYSIS_FIELDS.items()
    }
    for extra_field in ("feedback", "coaching_tip", "tone_score", "empathy_score", "clarity_score"):
        if extra_field in stored_analysis:
            analysis[extra_field] = stored_analysis.get(extra_field)
    analysis["intent"] = analysis["intent"] if analysis["intent"] is not None else case.intent
    analysis["sentiment"] = analysis["sentiment"] if analysis["sentiment"] is not None else case.sentiment
    analysis["urgency"] = analysis["urgency"] if analysis["urgency"] is not None else case.urgency
    analysis["escalation_risk"] = (
        analysis["escalation_risk"]
        if analysis["escalation_risk"] is not None
        else case.escalation_risk
    )
    analysis["key_issue"] = analysis["key_issue"] if analysis["key_issue"] is not None else case.key_issue

    cbr_metadata = {
        key: value
        for key, value in stored_analysis.items()
        if key.startswith("cbr_") or key in {"matched_case_ids", "analysis_source"}
    }
    messages = []
    if include_messages:
        messages = [
            {
                "message_id": message.message_id,
                "speaker": message.sender_type,
                "text": message.message,
                "language": message.language,
                "timestamp": message.timestamp.isoformat(),
            }
            for message in get_case_messages(session, case_id)
        ]

    return {
        "case_id": case.case_id,
        "customer_id": case.customer_id,
        "analysis": analysis,
        "cbr_metadata": cbr_metadata,
        "messages": messages,
    }