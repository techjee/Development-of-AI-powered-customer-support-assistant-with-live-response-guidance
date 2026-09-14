import os
import json
import time
import base64
import hashlib
import hmac
from threading import Lock
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Literal, Optional
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field
from dotenv import load_dotenv
from google import genai
from google.genai import types
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

# Import modules from local files
from vector_db import ComplaintRecord, PolicyVectorEngine, VectorCBREngine
from database import SessionLocal, ensure_auth_schema
from models import CaseEvent, Customer, SupportCase as SupportCaseModel, User
from services import (
    add_message,
    assign_agent,
    create_case,
    create_customer,
    create_case_event_once,
    get_case,
    get_case_messages,
    get_case_events,
    get_existing_message,
    list_cases,
    record_first_response,
    reopen_case,
    resolve_case,
    update_case,
)
from services.analysis import get_stored_case_analysis
from services.analytics import overall_summary
from services.routing import determine_department

load_dotenv(override=True)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    raise ValueError("GEMINI_API_KEY is not set in environment or .env file.")

AUTH_SECRET = os.getenv("AUTH_SECRET")
if not AUTH_SECRET:
    raise ValueError("AUTH_SECRET is not set in environment or .env file.")
AUTH_TOKEN_TTL_SECONDS = 8 * 60 * 60
bearer_scheme = HTTPBearer(auto_error=False)


class LoginRequest(BaseModel):
    username: str
    password: str
    role: Literal["human_agent", "admin"] = "human_agent"


def _create_token(username: str, role: str) -> str:
    payload = f"{username}|{role}|{int(time.time()) + AUTH_TOKEN_TTL_SECONDS}"
    encoded = base64.urlsafe_b64encode(payload.encode()).decode().rstrip("=")
    signature = hmac.new(AUTH_SECRET.encode(), encoded.encode(), hashlib.sha256).hexdigest()
    return f"{encoded}.{signature}"


def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
) -> dict:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=401, detail="Authentication required.")

    try:
        encoded, signature = credentials.credentials.split(".", 1)
        expected_signature = hmac.new(
            AUTH_SECRET.encode(), encoded.encode(), hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(signature, expected_signature):
            raise ValueError
        payload = base64.urlsafe_b64decode(encoded + "===").decode().split("|")
        username, role, expires_at = payload
        if int(expires_at) < int(time.time()) or role not in {"admin", "human_agent"}:
            raise ValueError
    except (ValueError, IndexError, TypeError, SQLAlchemyError):
        raise HTTPException(status_code=401, detail="Invalid or expired token.")

    return {"username": username, "role": role, "display_name": username.split("@", 1)[0]}


def require_admin(current_user: dict = Depends(get_current_user)) -> dict:
    if current_user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Admin access required.")
    return current_user


class TextTicketRequest(BaseModel):
    query: str = Field(..., description="Customer complaint text prompt")
    customer_id: Optional[str] = None
    case_id: Optional[str] = None
    language: Optional[Literal["en", "hi", "ta"]] = None


class HistoricalCaseUseRequest(BaseModel):
    historical_case_id: str


class AddCaseRequest(BaseModel):
    case_id: str
    category: str
    issue_description: str
    resolution_strategy: str
    recommended_reply: str
    escalation_risk: str
    success_rate: float


class CaseStatusUpdateRequest(BaseModel):
    status: Literal["NEW", "IN_PROGRESS", "WAITING", "RESOLVED"]
    resolution_summary: Optional[str] = None


class CaseMessageRequest(BaseModel):
    message: str
    language: Optional[str] = None


class CaseAssignmentRequest(BaseModel):
    agent_id: int


class CaseDepartmentTransferRequest(BaseModel):
    department: str


class CaseEventRequest(BaseModel):
    event_type: str
    event_details: Optional[dict] = None


class CaseEscalationRequest(BaseModel):
    reason: Literal[
        "Customer frustration / unresolved issue",
        "Repeated failed resolution",
        "Requires manager intervention",
        "Policy exception required",
        "Other",
    ]
    details: Optional[str] = None


# Static demo records for the administrator agent-detail workflow. These values
# are response-only and are never written to PostgreSQL.
DEMO_AGENT_PERFORMANCE = [
    {
        "agent_id": "agent_1",
        "agent_name": "Agent 1",
        "cases_handled": 42,
        "cases_resolved": 31,
        "cases_escalated": 5,
        "cases_pending": 6,
        "avg_resolution_time": "18 min",
    },
    {
        "agent_id": "agent_2",
        "agent_name": "Agent 2",
        "cases_handled": 37,
        "cases_resolved": 29,
        "cases_escalated": 3,
        "cases_pending": 5,
        "avg_resolution_time": "22 min",
    },
    {
        "agent_id": "agent_3",
        "agent_name": "Agent 3",
        "cases_handled": 51,
        "cases_resolved": 40,
        "cases_escalated": 6,
        "cases_pending": 5,
        "avg_resolution_time": "16 min",
    },
]

DEMO_AGENT_CASES = {
    "agent_1": [
        {
            "case_id": "DEMO-CASE-1001",
            "customer": "Demo Customer 1",
            "issue_type": "refund",
            "intent": "refund",
            "key_issue": "Refund is delayed after cancellation.",
            "department": "Accounts",
            "priority": "High",
            "priority_score": 78,
            "sentiment": "Negative",
            "urgency": "High",
            "escalation_risk": "medium",
            "status": "RESOLVED",
            "escalated": False,
            "escalation_reason": None,
            "resolution_time": "16 min",
            "created_at": "2026-09-10T09:15:00Z",
            "resolved_at": "2026-09-10T09:31:00Z",
            "resolution_summary": "Refund status was verified and the customer received the processing details.",
            "ai_recommendation_used": True,
            "ai_recommendation_rejected": False,
        },
        {
            "case_id": "DEMO-CASE-1002",
            "customer": "Demo Customer 2",
            "issue_type": "technical_issue",
            "intent": "technical_issue",
            "key_issue": "Customer cannot complete account setup.",
            "department": "Support",
            "priority": "Medium",
            "priority_score": 54,
            "sentiment": "Neutral",
            "urgency": "Medium",
            "escalation_risk": "low",
            "status": "IN_PROGRESS",
            "escalated": False,
            "escalation_reason": None,
            "resolution_time": None,
            "created_at": "2026-09-12T14:20:00Z",
            "resolved_at": None,
            "resolution_summary": None,
            "ai_recommendation_used": False,
            "ai_recommendation_rejected": True,
        },
    ],
    "agent_2": [
        {
            "case_id": "DEMO-CASE-2001",
            "customer": "Demo Customer 3",
            "issue_type": "billing",
            "intent": "billing",
            "key_issue": "Customer reports a duplicate charge.",
            "department": "Accounts",
            "priority": "Critical",
            "priority_score": 91,
            "sentiment": "Very Negative",
            "urgency": "Critical",
            "escalation_risk": "high",
            "status": "ESCALATED",
            "escalated": True,
            "escalation_reason": "Requires manager intervention",
            "resolution_time": None,
            "created_at": "2026-09-13T11:05:00Z",
            "resolved_at": None,
            "resolution_summary": None,
            "ai_recommendation_used": True,
            "ai_recommendation_rejected": False,
        },
    ],
    "agent_3": [
        {
            "case_id": "DEMO-CASE-3001",
            "customer": "Demo Customer 4",
            "issue_type": "delivery_delay",
            "intent": "delivery",
            "key_issue": "Order is delayed beyond the promised delivery date.",
            "department": "Support",
            "priority": "High",
            "priority_score": 73,
            "sentiment": "Negative",
            "urgency": "High",
            "escalation_risk": "medium",
            "status": "RESOLVED",
            "escalated": False,
            "escalation_reason": None,
            "resolution_time": "14 min",
            "created_at": "2026-09-08T10:10:00Z",
            "resolved_at": "2026-09-08T10:24:00Z",
            "resolution_summary": "Tracking was verified and the updated delivery status was provided.",
            "ai_recommendation_used": False,
            "ai_recommendation_rejected": False,
        },
        {
            "case_id": "DEMO-CASE-3002",
            "customer": "Demo Customer 5",
            "issue_type": "account_issue",
            "intent": "query",
            "key_issue": "Customer is waiting for account verification.",
            "department": "Support",
            "priority": "Low",
            "priority_score": 29,
            "sentiment": "Neutral",
            "urgency": "Low",
            "escalation_risk": "low",
            "status": "WAITING",
            "escalated": False,
            "escalation_reason": None,
            "resolution_time": None,
            "created_at": "2026-09-13T15:40:00Z",
            "resolved_at": None,
            "resolution_summary": None,
            "ai_recommendation_used": False,
            "ai_recommendation_rejected": False,
        },
        {
            "case_id": "DEMO-CASE-3003",
            "customer": "Demo Customer 6",
            "issue_type": "duplicate_charge",
            "intent": "billing",
            "key_issue": "Customer reports a duplicate payment charge.",
            "department": "Accounts",
            "priority": "Critical",
            "priority_score": 94,
            "sentiment": "Very Negative",
            "urgency": "Critical",
            "escalation_risk": "high",
            "status": "ESCALATED",
            "escalated": True,
            "escalation_reason": "Requires manager intervention",
            "resolution_time": None,
            "created_at": "2026-09-14T08:30:00Z",
            "resolved_at": None,
            "resolution_summary": None,
            "ai_recommendation_used": True,
            "ai_recommendation_rejected": False,
        },
    ],
}


class CaseSummaryResponse(BaseModel):
    summary: str


class CaseBriefResponse(BaseModel):
    detected_language: str
    briefing: str


@dataclass
class Message:
    speaker: str
    text: str


@dataclass
class ConversationState:
    history: list[Message] = field(default_factory=list)
    sentiment: str = "unknown"
    urgency: str = "unknown"
    escalation_risk: str = "unknown"
    key_issue: str = ""

    def add_message(self, speaker: str, text: str):
        self.history.append(Message(speaker=speaker, text=text))


@dataclass
class CoachingFeedback:
    tone_score: int
    empathy_score: int
    clarity_score: int
    coaching_tip: str


class HuggingFaceNLP:
    def __init__(self):
        self._sentiment_pipeline = None
        self._intent_pipeline = None

    def _get_sentiment_pipeline(self):
        from transformers import pipeline as build_pipeline
        if self._sentiment_pipeline is None:
            self._sentiment_pipeline = build_pipeline(
                "sentiment-analysis",
                model="distilbert-base-uncased-finetuned-sentiment",
            )
        return self._sentiment_pipeline

    def _get_intent_pipeline(self):
        from transformers import pipeline as build_pipeline
        if self._intent_pipeline is None:
            self._intent_pipeline = build_pipeline(
                "zero-shot-classification",
                model="facebook/bart-large-mnli",
            )
        return self._intent_pipeline

    @staticmethod
    def _normalize_sentiment(label: str) -> str:
        label = (label or "neutral").lower()
        if label.startswith("neg"):
            return "negative"
        if label.startswith("pos"):
            return "positive"
        return "neutral"

    @staticmethod
    def _normalize_intent(label: str) -> str:
        label = (label or "query").strip().lower().replace("-", "_")
        aliases = {
            "technical": "technical_issue",
            "technical_support": "technical_issue",
            "question": "query",
            "cancel": "cancellation",
            "cancellation": "cancellation",
            "refund": "refund",
            "purchase": "purchase",
            "order": "purchase",
            "feedback": "feedback",
            "complaint": "complaint",
        }
        return aliases.get(label, label if label in {"complaint", "query", "purchase", "technical_issue", "feedback", "cancellation", "refund"} else "query")

    @staticmethod
    def _fallback_analyze(text: str) -> dict:
        lowered = text.lower()
        negative_terms = (
            "disappointed", "frustrated", "angry", "unacceptable", "terrible", "horrible",
            "complaint", "delay", "delayed", "pending", "still hasn't", "taking too long",
            "crashing", "not working", "won't connect", "failed", "error"
        )
        positive_terms = ("satisfied", "happy", "great", "excellent", "thank you", "thanks", "resolved")
        intent_terms = {
            "refund": ("refund", "money back", "reimburse", "reimbursement"),
            "cancellation": ("cancel", "cancellation", "cancelled"),
            "technical_issue": ("crash", "crashing", "freeze", "freezing", "error", "won't connect", "not working"),
            "feedback": ("feedback", "suggest", "improve", "thank you", "thanks", "excellent", "great", "resolved"),
            "complaint": ("complaint", "disappointed", "frustrated", "angry", "unacceptable", "delay", "delayed", "pending", "still hasn't", "taking too long"),
            "purchase": ("buy", "purchase", "order"),
            "query": ("how", "what", "when", "where", "question", "reset", "password"),
        }

        sentiment = "negative" if any(term in lowered for term in negative_terms) else "positive" if any(term in lowered for term in positive_terms) else "neutral"
        intent = next((name for name, terms in intent_terms.items() if any(term in lowered for term in terms)), "query")
        sentiment_score = {"negative": 1, "neutral": 3, "positive": 5}.get(sentiment, 3)
        return {
            "sentiment": sentiment,
            "sentiment_score": sentiment_score,
            "customer_intent": intent,
        }

    def analyze(self, text: str) -> dict:
        if not text or not text.strip():
            return {"sentiment": "neutral", "sentiment_score": 3, "customer_intent": "query"}

        try:
            sentiment_result = self._get_sentiment_pipeline()(text, truncation=True)[0]
            sentiment = self._normalize_sentiment(sentiment_result.get("label", "neutral"))
            sentiment_score = {"negative": 1, "neutral": 3, "positive": 5}.get(sentiment, 3)

            intent_result = self._get_intent_pipeline()(
                text,
                candidate_labels=["complaint", "query", "purchase", "technical_issue", "feedback", "cancellation", "refund"],
                multi_label=False,
                hypothesis_template="This text is about {}.",
            )
            intent = self._normalize_intent(intent_result.get("labels", ["query"])[0])
            lowered = text.lower()
            if sentiment == "positive" and any(phrase in lowered for phrase in ("thank you", "thanks", "excellent", "great", "resolved")):
                intent = "feedback"
            elif "refund" in lowered and any(phrase in lowered for phrase in ("cancel", "cancelled", "cancellation")):
                intent = "refund"
            return {
                "sentiment": sentiment,
                "sentiment_score": sentiment_score,
                "customer_intent": intent,
            }
        except Exception as error:
            print(f"[Warning] Hugging Face inference failed: {error}")
            return self._fallback_analyze(text)


class AICoach:
    def __init__(self, client=None, model: Optional[str] = None):
        self.client = client
        self.model = model or os.getenv("GEMINI_MODEL", "gemini-3.6-flash")

    def _parse_json(self, text: str) -> dict:
        text = text.strip()
        if text.startswith("```"):
            lines = text.splitlines()
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            text = "\n".join(lines).strip()
        if text.lower().startswith("json"):
            text = text[4:].strip()
        return json.loads(text)


def generate_coaching_feedback(agent_message: str, customer_message: str) -> CoachingFeedback:
    customer_text = (customer_message or "").lower()
    agent_text = (agent_message or "").lower()

    tone_score = 2
    empathy_score = 2
    clarity_score = 2

    apology_phrases = ("sorry", "apologize", "apologies")
    empathy_phrases = ("understand", "frustrating", "disappointed", "how frustrating", "i understand")
    action_phrases = ("i checked", "i will", "next update", "next step", "can help", "will review", "will confirm")
    product_terms = ("refund", "delay", "delivery", "wifi", "crashing", "freeze", "cancelled", "order")

    if any(phrase in agent_text for phrase in apology_phrases):
        tone_score += 1
        empathy_score += 1
    if any(phrase in agent_text for phrase in empathy_phrases):
        empathy_score += 1
    if any(phrase in agent_text for phrase in action_phrases):
        clarity_score += 1
        tone_score += 1
    if any(term in customer_text for term in product_terms) and any(term in agent_text for term in product_terms):
        empathy_score += 1
        clarity_score += 1
    if any(vague in agent_text for vague in ("being processed", "your request is being processed", "we are reviewing")):
        clarity_score -= 1
        empathy_score -= 1

    if "sorry" not in agent_text and any(negative in customer_text for negative in ("disappointed", "frustrated", "angry", "unacceptable", "delay", "refund")):
        empathy_score -= 1

    tone_score = max(1, min(5, tone_score))
    empathy_score = max(1, min(5, empathy_score))
    clarity_score = max(1, min(5, clarity_score))

    if clarity_score <= 2 or empathy_score <= 2:
        coaching_tip = "Acknowledge the customer's issue directly, show empathy, and include a concrete next step or timeline."
    elif tone_score <= 3:
        coaching_tip = "Polish the tone by acknowledging frustration and stating what you can do next with confidence."
    else:
        coaching_tip = "Strong response: you acknowledged the issue, showed empathy, and gave a clear next step."

    return CoachingFeedback(
        tone_score=tone_score,
        empathy_score=empathy_score,
        clarity_score=clarity_score,
        coaching_tip=coaching_tip,
    )


def determine_next_best_action(
    sentiment,
    intent,
    urgency,
    escalation_risk,
    key_issue,
    product_info=None,
    similar_cases=None,
):
    high_risk = (
        escalation_risk == "high"
        or urgency == "high"
        or sentiment == "negative"
    )

    if intent in ["cancellation", "refund"]:
        if "delivery" in key_issue.lower() or "delay" in key_issue.lower():
            if similar_cases:
                return {
                    "action": "retention_intervention",
                    "recommendation": "Check for a suitable alternative seller or faster delivery option before processing cancellation.",
                    "reason": "The customer's dissatisfaction appears to be caused by delivery delay.",
                }
            return {
                "action": "alternative_check",
                "recommendation": "Check whether the same or a comparable product is available with faster delivery.",
                "reason": "An alternative may address the customer's actual issue.",
            }
        if "product" in key_issue.lower() or "defect" in key_issue.lower():
            return {
                "action": "replacement_or_resolution",
                "recommendation": "Check replacement, warranty, or troubleshooting options before processing cancellation.",
                "reason": "The customer's dissatisfaction is related to the product.",
            }
        return {
            "action": "understand_cancellation_reason",
            "recommendation": "Identify the customer's specific reason for cancellation before suggesting an alternative.",
            "reason": "A suitable retention action depends on the reason for leaving.",
        }

    if high_risk and intent == "complaint":
        return {
            "action": "escalate_or_prioritize",
            "recommendation": "Acknowledge the customer's frustration and prioritize the issue or escalate it when necessary.",
            "reason": "The interaction shows elevated dissatisfaction or risk.",
        }
    if intent == "technical_issue":
        return {
            "action": "troubleshoot",
            "recommendation": "Provide guided troubleshooting based on the customer's issue.",
            "reason": "The customer requires technical assistance.",
        }
    return {
        "action": "normal_support",
        "recommendation": "Answer the customer's query clearly and provide the next relevant step.",
        "reason": "No high-risk intervention is currently required.",
    }


@dataclass
class SupportCase:
    customer_id: str
    case_id: str
    created_at: str = ""
    updated_at: str = ""
    resolved_at: Optional[str] = None
    status: str = "NEW"
    messages: list[dict] = field(default_factory=list)
    latest_analysis: Optional[dict] = None
    department: Optional[str] = None
    routing_reason: Optional[str] = None
    escalation_status: Optional[str] = None
    escalation_reason: Optional[str] = None
    escalated_at: Optional[str] = None
    escalation_actor_id: Optional[int] = None


class SupportCaseRegistry:
    """Database-backed live case state keyed by customer and case identifiers."""

    def __init__(self):
        pass

    @property
    def cases(self) -> dict[tuple[str, str], SupportCase]:
        return {
            (case.customer_id, case.case_id): case
            for case in self._list_support_cases()
        }

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    def record_customer_message(
        self,
        customer_id: Optional[str],
        case_id: Optional[str],
        query: str,
        analysis: dict
    ) -> Optional[dict]:
        if not customer_id or not case_id:
            return None

        with SessionLocal() as session:
            if session.get(Customer, customer_id) is None:
                create_customer(
                    session,
                    customer_id=customer_id,
                    name=customer_id,
                )
            case = get_case(session, case_id)
            case_created = case is None
            if case_created:
                case = create_case(
                    session,
                    case_id=case_id,
                    customer_id=customer_id,
                )
                self._record_event(
                    case_id=case_id,
                    actor_type="system",
                    event_type="CASE_CREATED",
                    event_details={"customer_id": customer_id},
                )
            elif case.customer_id != customer_id:
                raise ValueError("Case ID is already assigned to another customer.")

            department, routing_reason = determine_department(analysis, query)
            updated_case = update_case(
                session,
                case_id,
                department=department,
                routing_reason=routing_reason,
                intent=analysis.get("customer_intent"),
                sentiment=analysis.get("sentiment"),
                urgency=analysis.get("urgency"),
                escalation_risk=analysis.get("escalation_risk"),
                key_issue=query,
                ai_assisted=True,
            )
            if routing_reason:
                self._record_event(
                    case_id=case_id,
                    actor_type="system",
                    event_type="DEPARTMENT_ROUTED",
                    event_details={
                        "department": department,
                        "routing_reason": routing_reason,
                    },
                )
            self._record_event(
                case_id=case_id,
                actor_type="ai_assistant",
                event_type="AI_ANALYSIS",
                event_details={"query": query, "analysis": analysis},
            )
            return self._case_with_priority(self._to_support_case(updated_case, analysis))

    def update_status(self, customer_id: str, case_id: str, status: str, resolution_summary: str | None = None) -> Optional[dict]:
        with SessionLocal() as session:
            case = get_case(session, case_id)
            if case is None or case.customer_id != customer_id:
                return None
            previous_status = case.status
            if status == "RESOLVED":
                case = resolve_case(session, case_id, resolution_summary=resolution_summary)
            elif status == "NEW" and case.status == "RESOLVED":
                case = reopen_case(session, case_id)
            else:
                case = update_case(session, case_id, status=status)
            if status == "RESOLVED" and previous_status != "RESOLVED":
                self._record_event(
                    case_id=case_id,
                    actor_type="system",
                    event_type="CASE_RESOLVED",
                    event_details={"resolution_summary": resolution_summary},
                )
            elif status == "NEW" and previous_status == "RESOLVED":
                self._record_event(
                    case_id=case_id,
                    actor_type="system",
                    event_type="CASE_REOPENED",
                    event_details={},
                )
            return self._case_with_priority(self._to_support_case(case))

    def get_case(self, customer_id: str, case_id: str) -> Optional[dict]:
        with SessionLocal() as session:
            case = get_case(session, case_id)
            if case is None or case.customer_id != customer_id:
                return None
            return self._case_with_priority(self._to_support_case(case))

    def assign_agent(self, customer_id: str, case_id: str, agent_id: int | None) -> Optional[dict]:
        with SessionLocal() as session:
            case = get_case(session, case_id)
            if case is None or case.customer_id != customer_id:
                return None
            previous_agent_id = case.assigned_agent_id
            case = assign_agent(session, case_id, agent_id)
            self._record_event(
                case_id=case_id,
                actor_type="system",
                event_type="CASE_REASSIGNED" if previous_agent_id is not None else "CASE_ASSIGNED",
                event_details={"assigned_agent_id": agent_id, "previous_agent_id": previous_agent_id},
            )
            return self._case_with_priority(self._to_support_case(case))

    def resolve_case(self, customer_id: str, case_id: str, resolution_summary: str | None = None) -> Optional[dict]:
        with SessionLocal() as session:
            case = get_case(session, case_id)
            if case is None or case.customer_id != customer_id:
                return None
            case = resolve_case(session, case_id, resolution_summary=resolution_summary)
            self._record_event(
                case_id=case_id,
                actor_type="system",
                event_type="CASE_RESOLVED",
                event_details={"resolution_summary": resolution_summary},
            )
            return self._case_with_priority(self._to_support_case(case))

    def reopen_case(self, customer_id: str, case_id: str) -> Optional[dict]:
        with SessionLocal() as session:
            case = get_case(session, case_id)
            if case is None or case.customer_id != customer_id:
                return None
            case = reopen_case(session, case_id)
            self._record_event(
                case_id=case_id,
                actor_type="system",
                event_type="CASE_REOPENED",
                event_details={},
            )
            return self._case_with_priority(self._to_support_case(case))

    def escalate_case(
        self,
        customer_id: str,
        case_id: str,
        *,
        reason: str,
        actor_id: int | None,
        details: str | None = None,
    ) -> Optional[dict]:
        with SessionLocal() as session:
            case = get_case(session, case_id)
            if case is None or case.customer_id != customer_id:
                return None
            if case.status == "RESOLVED":
                raise ValueError("Resolved cases cannot be escalated.")
            escalated_at = datetime.now(timezone.utc)
            case = update_case(
                session,
                case_id,
                escalation_status="ESCALATED",
                escalation_reason=reason,
                escalated_at=escalated_at,
                escalation_actor_id=actor_id,
                ai_escalation=False,
            )
            self._record_event(
                case_id=case_id,
                actor_type="human_agent",
                actor_id=actor_id,
                event_type="CASE_ESCALATED",
                event_details={
                    "reason": reason,
                    "details": details,
                    "escalated_at": escalated_at.isoformat(),
                },
            )
            return self._case_with_priority(self._to_support_case(case))

    @staticmethod
    def _record_event(*, case_id: str, actor_type: str, event_type: str, actor_id: int | None = None, event_details: dict | None = None) -> None:
        with SessionLocal() as session:
            create_case_event_once(
                session,
                case_id=case_id,
                actor_type=actor_type,
                actor_id=actor_id,
                event_type=event_type,
                event_details=event_details,
            )

    @staticmethod
    def _to_support_case(
        case,
        analysis: Optional[dict] = None,
        session=None,
        load_stored_analysis: bool = True,
    ) -> SupportCase:
        analysis = analysis or {}
        if not analysis and load_stored_analysis:
            if session is None:
                with SessionLocal() as load_session:
                    stored_events = get_case_events(
                        load_session,
                        case.case_id,
                        event_type="AI_ANALYSIS",
                    )
            else:
                stored_events = get_case_events(
                    session,
                    case.case_id,
                    event_type="AI_ANALYSIS",
                )
            if stored_events:
                analysis = (stored_events[-1].event_details or {}).get("analysis", {})
        if not analysis:
            analysis = {
                "selected_category": case.department or "General Support",
                "customer_intent": case.intent or "Requesting issue resolution",
                "sentiment": case.sentiment or "Neutral",
                "urgency": case.urgency or "Low",
                "escalation_risk": case.escalation_risk or "low",
                "recommended_next_step": case.key_issue or "Review the case and provide the next resolution step.",
            }
        created_at = case.created_at.isoformat() if case.created_at else ""
        updated_at = case.updated_at.isoformat() if case.updated_at else ""
        resolved_at = case.resolved_at.isoformat() if case.resolved_at else None
        return SupportCase(
            customer_id=case.customer_id,
            case_id=case.case_id,
            created_at=created_at,
            updated_at=updated_at,
            resolved_at=resolved_at,
            status=case.status,
            messages=[],
            latest_analysis=analysis,
            department=case.department,
            routing_reason=case.routing_reason,
            escalation_status=case.escalation_status,
            escalation_reason=case.escalation_reason,
            escalated_at=case.escalated_at.isoformat() if case.escalated_at else None,
            escalation_actor_id=case.escalation_actor_id,
        )

    def _list_support_cases(self, active_only: bool = False) -> list[SupportCase]:
        with SessionLocal() as session:
            if active_only:
                cases = list(
                    session.scalars(
                        select(SupportCaseModel)
                        .where(SupportCaseModel.status.in_(("NEW", "IN_PROGRESS", "WAITING")))
                        .order_by(SupportCaseModel.created_at, SupportCaseModel.case_id)
                    )
                )
            else:
                cases = list_cases(session)
            if not cases:
                return []
            analysis_by_case = {}
            if not active_only:
                case_ids = [case.case_id for case in cases]
                analysis_events = list(
                    session.scalars(
                        select(CaseEvent)
                        .where(
                            CaseEvent.case_id.in_(case_ids),
                            CaseEvent.event_type == "AI_ANALYSIS",
                        )
                        .order_by(CaseEvent.timestamp, CaseEvent.event_id)
                    )
                )
                for event in analysis_events:
                    analysis_by_case[event.case_id] = (event.event_details or {}).get("analysis", {})
            return [
                self._to_support_case(
                    case,
                    analysis=analysis_by_case.get(case.case_id),
                    session=session,
                    load_stored_analysis=not active_only,
                )
                for case in cases
            ]

    def calculate_priority(self, case: SupportCase, now: Optional[datetime] = None) -> dict:
        now = now or datetime.now(timezone.utc)
        created_at = datetime.fromisoformat(case.created_at)
        waiting_minutes = max(0.0, (now - created_at).total_seconds() / 60)
        analysis = case.latest_analysis or {}

        risk_points = {
            "critical": 40,
            "high": 30,
            "medium": 20,
            "low": 10,
        }.get(str(analysis.get("escalation_risk", "low")).lower(), 10)
        urgency_points = {
            "critical": 30,
            "high": 20,
            "medium": 10,
            "low": 0,
        }.get(str(analysis.get("urgency", "low")).lower(), 0)

        category = str(analysis.get("selected_category", "")).lower()
        if any(term in category for term in ("safety", "fraud", "chargeback", "legal", "recall")):
            severity_label, severity_points = "critical", 25
        elif any(term in category for term in ("damage", "defect", "security", "technical", "lockout")):
            severity_label, severity_points = "high", 18
        elif any(term in category for term in ("delay", "refund", "billing", "payment", "missing")):
            severity_label, severity_points = "medium", 10
        else:
            severity_label, severity_points = "low", 5

        repeat_contact_points = min(max(len(case.messages) - 1, 0) * 5, 20)
        waiting_points = min(waiting_minutes / 60, 40)
        score = round(
            risk_points
            + urgency_points
            + severity_points
            + repeat_contact_points
            + waiting_points,
            2
        )
        if score >= 100:
            priority_label = "CRITICAL"
        elif score >= 70:
            priority_label = "HIGH"
        elif score >= 40:
            priority_label = "MEDIUM"
        else:
            priority_label = "LOW"

        return {
            "priority_score": score,
            "priority_label": priority_label,
            "priority_factors": {
                "escalation_risk_points": risk_points,
                "urgency_points": urgency_points,
                "waiting_minutes": round(waiting_minutes, 2),
                "waiting_time_points": round(waiting_points, 2),
                "issue_severity": severity_label,
                "issue_severity_points": severity_points,
                "message_count": len(case.messages),
                "repeat_contact_points": repeat_contact_points,
            },
        }

    def _case_with_priority(self, case: SupportCase, now: Optional[datetime] = None) -> dict:
        case_data = asdict(case)
        if case.status != "RESOLVED":
            case_data.update(self.calculate_priority(case, now=now))
        return case_data

    def list_active_cases(self) -> list[dict]:
        now = datetime.now(timezone.utc)
        active_cases = self._list_support_cases(active_only=True)
        prioritized_cases = [self._case_with_priority(case, now=now) for case in active_cases]
        return sorted(
            prioritized_cases,
            key=lambda case: (-case["priority_score"], case["created_at"])
        )


def analyze_customer_signal(query: str, similar_cases: list[dict]) -> dict:
    text = query.lower()
    negative_terms = ("disappointed", "frustrated", "angry", "unacceptable", "terrible", "horrible", "complaint")
    positive_terms = ("satisfied", "happy", "great", "excellent", "thank you")
    high_urgency_terms = ("urgent", "immediately", "asap", "manager", "emergency", "still hasn't")
    threat_terms = ("lawsuit", "legal", "chargeback", "report", "fraud")
    intent_terms = {
        "refund": ("refund", "money back", "reimburse", "reimbursement"),
        "cancellation": ("cancel", "cancellation", "cancelled"),
        "technical_issue": ("wifi", "freeze", "freezing", "error", "won't connect", "not working", "crash", "crashing"),
        "complaint": ("complaint", "disappointed", "frustrated", "angry", "unacceptable", "delay", "delayed", "pending", "still hasn't", "taking too long", "issue"),
        "purchase": ("buy", "purchase", "order"),
        "feedback": ("feedback", "suggest", "improve", "thank you", "thanks", "excellent", "great", "resolved"),
        "query": ("how", "what", "when", "where", "question", "reset", "password"),
    }

    sentiment = "negative" if any(term in text for term in negative_terms) else "positive" if any(term in text for term in positive_terms) else "neutral"
    urgency = "high" if any(term in text for term in high_urgency_terms) else "medium"
    escalation = "high" if any(term in text for term in threat_terms) else "low"
    intent = next((name for name, terms in intent_terms.items() if any(term in text for term in terms)), "query")
    if intent in {"complaint", "refund", "cancellation"} and sentiment == "negative":
        escalation = "high"
    key_issue = query
    next_action = determine_next_best_action(
        sentiment=sentiment,
        intent=intent,
        urgency=urgency,
        escalation_risk=escalation,
        key_issue=key_issue,
    )

    return {
        "selected_category": intent,
        "matched_case_ids": [case["case_id"] for case in similar_cases if "case_id" in case],
        "synthesized_strategy": next_action["recommendation"],
        "drafted_response": "I am sorry you are experiencing this issue. I understand your concern and will review it immediately, then provide a clear resolution or next step.",
        "escalation_risk": escalation,
        "sentiment": sentiment,
        "sentiment_score": 1 if sentiment == "negative" else 5 if sentiment == "positive" else 3,
        "urgency": urgency,
        "urgency_score": 4 if urgency == "high" else 3,
        "customer_intent": intent,
        "key_issue": key_issue,
        "recommended_next_step": next_action["recommendation"],
        "analysis_source": "local fallback (Gemini quota unavailable)",
    }


def normalize_analysis(analysis: dict, query: str, similar_cases: list[dict]) -> dict:
    normalized = dict(analysis)
    sentiment = str(normalized.get("sentiment", "neutral")).lower()
    normalized["sentiment"] = (
        "negative" if "negative" in sentiment else
        "positive" if "positive" in sentiment else
        "neutral"
    )
    intent = str(normalized.get("customer_intent", "query")).lower().replace(" ", "_")
    intent_aliases = {
        "technical": "technical_issue",
        "technical_support": "technical_issue",
        "question": "query",
        "complaint_issue": "complaint",
    }
    normalized["customer_intent"] = intent_aliases.get(intent, intent if intent in {
        "cancellation", "refund", "purchase", "technical_issue", "feedback", "complaint", "query"
    } else analyze_customer_signal(query, similar_cases)["customer_intent"])
    normalized["selected_category"] = normalized["customer_intent"]
    for field_name in ("urgency", "escalation_risk"):
        value = str(normalized.get(field_name, "low")).lower()
        normalized[field_name] = "high" if value in {"high", "critical", "extreme", "extremely high"} else "medium" if value == "medium" else "low"
    normalized["key_issue"] = str(normalized.get("key_issue") or query)
    return normalized


def customer_response_fallback(language: str, conversation_state: ConversationState) -> str:
    issue = conversation_state.key_issue or "your concern"
    if language == "hi":
        return f"आपकी समस्या के लिए हमें खेद है। हमने आपके मामले की समीक्षा की है: {issue} कृपया निश्चिंत रहें, हम इसे प्राथमिकता से देख रहे हैं और आपको अगला स्पष्ट समाधान बताएंगे।"
    if language == "ta":
        return f"உங்களுக்கு ஏற்பட்ட சிரமத்திற்கு வருந்துகிறோம். உங்கள் வழக்கை நாங்கள் பரிசீலித்துள்ளோம்: {issue} தயவுசெய்து உறுதியாக இருங்கள், இதற்கு முன்னுரிமையுடன் தீர்வு காணும் அடுத்த நடவடிக்கையை உங்களுக்கு தெரிவிப்போம்."
    return f"I am sorry you are experiencing this issue. We reviewed your case regarding {issue}. Please be assured that we are prioritizing it and will provide the next clear resolution step."


def detect_customer_language(text: str) -> str:
    devanagari_count = sum("\u0900" <= character <= "\u097f" for character in text)
    tamil_count = sum("\u0b80" <= character <= "\u0bff" for character in text)
    if devanagari_count > tamil_count and devanagari_count:
        return "hi"
    if tamil_count:
        return "ta"
    return "en"


class CBRSystemPipeline:
    def __init__(self):
        ensure_auth_schema()
        self.api_key = GEMINI_API_KEY
        self.client = genai.Client(api_key=self.api_key)
        self.model = os.getenv("GEMINI_MODEL", "gemini-3.6-flash")
        self.cbr_very_high_threshold = float(os.getenv("CBR_VERY_HIGH_THRESHOLD", "0.75"))
        self.cbr_similar_threshold = float(os.getenv("CBR_SIMILAR_THRESHOLD", "0.40"))
        self.policy_similarity_threshold = float(os.getenv("POLICY_SIMILARITY_THRESHOLD", "0.45"))
        self.nlp = HuggingFaceNLP()
        
        # Initialize sub-modules
        self.vector_db = VectorCBREngine()
        self.policy_vector_db = PolicyVectorEngine(
            similarity_threshold=self.policy_similarity_threshold,
            encoder=self.vector_db.encoder,
        )
        self.case_registry = SupportCaseRegistry()
        self._load_resolved_cases_into_cbr()


    def _historical_record(self, case, session=None) -> ComplaintRecord:
        resolution = case.resolution_summary or "Successfully resolved customer support case."
        customer_context = ""
        successful_response = resolution
        if session is None:
            with SessionLocal() as load_session:
                return self._historical_record(case, session=load_session)
        messages = get_case_messages(session, case.case_id)
        customer_messages = [message.message for message in messages if message.sender_type == "customer"]
        agent_messages = [
            message.message
            for message in messages
            if message.sender_type in {"human_agent", "ai_assistant"}
        ]
        if customer_messages:
            customer_context = " Conversation context: " + " ".join(customer_messages[-3:])
        if agent_messages:
            successful_response = agent_messages[-1]
        return ComplaintRecord(
            case_id=case.case_id,
            category=case.intent or case.department or "General Support",
            issue_description=(case.key_issue or case.intent or "Resolved customer support case") + customer_context,
            resolution_strategy=resolution,
            recommended_reply=successful_response,
            escalation_risk=case.escalation_risk or "low",
            success_rate=1.0,
            resolved=True,
            successfully_resolved=True,
            intent=case.intent or "",
            key_issue=case.key_issue or "",
            context=customer_context,
            department=case.department or "",
        )

    @staticmethod
    def _is_valid_historical_case(case: dict) -> bool:
        return bool(
            case.get("resolved", case.get("resolution_status") in {"RESOLVED", "SUCCESS", "COMPLETED"})
            and case.get("successfully_resolved", True)
            and float(case.get("success_rate", 0) or 0) > 0
            and case.get("recommended_reply")
        )

    def _classify_cbr_match(self, cases: list[dict]) -> tuple[str, Optional[dict]]:
        valid_cases = [case for case in cases if self._is_valid_historical_case(case)]
        if not valid_cases:
            return "none", None
        best_case = valid_cases[0]
        similarity = float(best_case.get("normalized_similarity", best_case.get("raw_score", 0)))
        if similarity >= self.cbr_very_high_threshold:
            return "strong", best_case
        if similarity >= self.cbr_similar_threshold:
            return "similar", best_case
        return "none", None

    def _annotate_cbr_matches(self, cases: list[dict]) -> list[dict]:
        for case in cases:
            normalized_similarity = float(
                case.get("normalized_similarity", case.get("raw_score", case.get("similarity_score", 0)))
            )
            case["raw_score"] = float(case.get("raw_score", normalized_similarity))
            case["normalized_similarity"] = normalized_similarity
            case["similarity_score"] = normalized_similarity
            case["match_type"] = (
                "strong" if normalized_similarity >= self.cbr_very_high_threshold
                else "similar" if normalized_similarity >= self.cbr_similar_threshold
                else "none"
            )
        return cases

    def ingest_resolved_case(self, case_id: str) -> bool:
        with SessionLocal() as session:
            case = get_case(session, case_id)
            if case is None or case.status != "RESOLVED" or case.resolution_status not in {
                "RESOLVED", "SUCCESS", "COMPLETED"
            }:
                return False
            already_indexed = any(record.case_id == case.case_id for record in self.vector_db.records)
            self.vector_db.add_record(self._historical_record(case))
            return not already_indexed

    def _load_resolved_cases_into_cbr(self) -> None:
        with SessionLocal() as session:
            resolved_cases = list_cases(session, status="RESOLVED")
            records = [
                self._historical_record(case, session=session)
                for case in resolved_cases
                if case.resolution_status in {"RESOLVED", "SUCCESS", "COMPLETED"}
            ]
        self.vector_db.add_records(records)

    @staticmethod
    def _conversation_state(customer_id: Optional[str], case_id: Optional[str]) -> ConversationState:
        state = ConversationState()
        if not customer_id or not case_id:
            return state
        with SessionLocal() as session:
            case = get_case(session, case_id)
            if case is None:
                return state
            if case.customer_id != customer_id:
                raise ValueError("Case ID is already assigned to another customer.")
            state.sentiment = case.sentiment or "unknown"
            state.urgency = case.urgency or "unknown"
            state.escalation_risk = case.escalation_risk or "unknown"
            state.key_issue = case.key_issue or ""
            for message in get_case_messages(session, case_id):
                state.add_message(message.sender_type, message.message)
        return state

    def summarize_case(self, customer_id: str, case_id: str) -> str:
        with SessionLocal() as session:
            case = get_case(session, case_id)
            if case is None or case.customer_id != customer_id:
                raise HTTPException(status_code=404, detail="Support case not found.")
            risk = (case.escalation_risk or "").lower()
            if risk not in {"high", "critical"} and not case.ai_escalation:
                raise HTTPException(status_code=409, detail="Case is not escalated.")
            messages = get_case_messages(session, case_id)
            events = get_case_events(session, case_id)
            conversation = "\n".join(
                f"{message.sender_type}: {message.message}" for message in messages
            ) or "No conversation recorded."
            actions = "\n".join(
                f"{event.event_type}: {event.event_details or {}}" for event in events
            ) or "No case events recorded."
            recommendation = case.resolution_summary or case.key_issue or "No recommendation recorded."
            prompt = f"""
Create a concise operational escalation summary for a support agent.
Customer/problem: {customer_id} / {case.key_issue or 'No key issue recorded'}
Key issue: {case.key_issue or 'Not recorded'}
Intent: {case.intent or 'Not recorded'}
Conversation:
{conversation}
Actions already taken:
{actions}
AI recommendation: {recommendation}
Escalation reason/risk: {case.escalation_risk or 'Not recorded'}
Current department: {case.department or 'Not recorded'}
Suggested next action: Provide the safest immediate resolution step and escalation owner.

Return a concise plain-text summary with those headings.
"""
        try:
            response = self.client.models.generate_content(
                model=self.model,
                contents=prompt,
                config=types.GenerateContentConfig(temperature=0.2),
            )
            return response.text.strip()
        except Exception:
            return (
                f"Customer/problem: {customer_id} / {case.key_issue or 'Not recorded'}\n"
                f"Key issue: {case.key_issue or 'Not recorded'}\n"
                f"Intent: {case.intent or 'Not recorded'}\n"
                f"Important conversation context: {conversation}\n"
                f"Actions already taken: {actions}\n"
                f"AI recommendation: {recommendation}\n"
                f"Escalation reason/risk: {case.escalation_risk or 'Not recorded'}\n"
                f"Current department: {case.department or 'Not recorded'}\n"
                "Suggested next action: Review the escalation and assign the next resolution owner."
            )

    def case_brief(self, customer_id: str, case_id: str) -> dict:
        with SessionLocal() as session:
            case = get_case(session, case_id)
            if case is None or case.customer_id != customer_id:
                raise HTTPException(status_code=404, detail="Support case not found.")
            messages = get_case_messages(session, case_id)
            detected_language = next(
                (message.language for message in reversed(messages) if message.sender_type == "customer" and message.language),
                detect_customer_language(messages[-1].message if messages else ""),
            )
            conversation = "\n".join(
                f"{message.sender_type}: {message.message}" for message in messages
            ) or "No conversation recorded."
            latest_customer_message = next(
                (message.message for message in reversed(messages) if message.sender_type == "customer"),
                "No customer message recorded.",
            )
            latest_response = next(
                (message.message for message in reversed(messages) if message.sender_type == "ai_assistant"),
                "No generated response recorded.",
            )
            prompt = f"""
Create a short, readable English case brief for a human support agent.
Translate BOTH parts below into English and include both in 2-3 concise sentences:
1. What the customer is asking.
2. What the generated AI response says to the customer.
The second part is mandatory even when the generated response is in Hindi or Tamil.
Use exactly these labels: "Customer asks:" and "Generated response says:".
Do not repeat the original-language text. Do not provide recommendations, actions,
department transfers, sentiment labels, risk levels, or a case summary.
Preserve names, amounts, dates, and important details from the original messages.

Detected customer language: {detected_language}
Customer conversation:
{conversation}
Latest customer request:
{latest_customer_message}
Latest generated response:
{latest_response}
"""
        try:
            response = self.client.models.generate_content(
                model=self.model,
                contents=prompt,
                config=types.GenerateContentConfig(temperature=0.2),
            )
            briefing = response.text.strip()
        except Exception:
            briefing = (
                f"Customer asks: {latest_customer_message} "
                f"Generated response says: {latest_response}"
            )
        language_names = {"en": "English", "hi": "Hindi", "ta": "Tamil"}
        return {"detected_language": language_names.get(detected_language, detected_language), "briefing": briefing}

    def process_ticket(
        self, 
        user_query: str, 
        customer_id: Optional[str] = None,
        case_id: Optional[str] = None,
        language: Optional[str] = None,
        selected_historical_case: Optional[dict] = None,
        persist_case: bool = True,
        existing_analysis: Optional[dict] = None,
    ) -> dict:
        detected_language = language or detect_customer_language(user_query)
        conversation_state = self._conversation_state(customer_id, case_id)
        conversation_history = "\n".join(
            f"{message.speaker}: {message.text}" for message in conversation_state.history
        ) or "No previous conversation recorded."

        policy_query = f"{user_query}\n{conversation_history}"
        try:
            retrieved_policies = self.policy_vector_db.search_relevant(policy_query, top_k=1)
        except Exception as error:
            retrieved_policies = []
            print(f"[Warning] Policy vector search error: {str(error)}")
        policy_context = retrieved_policies[0] if retrieved_policies else None

        # Retrieve historical support context for each newly submitted customer message.
        # Opening an existing case still does not call this method.
        if selected_historical_case:
            retrieved_cases = [selected_historical_case]
        else:
            try:
                retrieved_cases = self.vector_db.search_similar(
                    query=user_query,
                    top_k=3,
                    threshold=self.cbr_similar_threshold,
                )
            except Exception as e:
                retrieved_cases = []
                print(f"[Warning] Vector DB search error: {str(e)}")
        retrieved_cases = self._annotate_cbr_matches(retrieved_cases)

        cbr_match_type, cbr_match = self._classify_cbr_match(retrieved_cases)
        cbr_context = [selected_historical_case] if selected_historical_case else [
            case for case in retrieved_cases
            if self._is_valid_historical_case(case)
        ]
        cbr_tracking = {
            "cbr_match_found": cbr_match is not None,
            "cbr_raw_score": float(cbr_match.get("raw_score", 0)) if cbr_match else 0.0,
            "cbr_similarity_score": float(cbr_match.get("normalized_similarity", 0)) if cbr_match else 0.0,
            "cbr_normalized_similarity": float(cbr_match.get("normalized_similarity", 0)) if cbr_match else 0.0,
            "cbr_match_type": cbr_match_type,
            "cbr_source_case_id": cbr_match.get("case_id") if cbr_match else None,
            "cbr_response_reused": False,
            "ai_call_avoided": False,
        }
        similar_cases = cbr_context

        # Reuse and revise using the current complaint, historical cases, and policy context.
        synthesis_prompt = f"""
You are an expert AI Customer Support CBR Engine.
Synthesize the incoming complaint using historical case precedents and company policy.

NEW CUSTOMER QUERY:
"{user_query}"

EXISTING CONVERSATION HISTORY:
{conversation_history}

CUSTOMER RESPONSE LANGUAGE:
Write only the drafted_response value in {detected_language} (en = English, hi = Hindi, ta = Tamil). Keep all analysis labels in their required notebook values.

RETRIEVED HISTORICAL CASES (CBR SUPPORTING CONTEXT ONLY):
{json.dumps(similar_cases, indent=2)}

RELATED COMPANY POLICY (SUPPORTING CONTEXT):
{json.dumps(policy_context, indent=2) if policy_context else "No related policy found."}

CURRENT AI ANALYSIS:
{json.dumps(existing_analysis, indent=2) if existing_analysis else "Generate analysis for this request as part of the response."}

When a historical case is provided, use it only as supporting context. Adapt its
strategy and reply to the current customer; do not copy customer-specific details.
Follow the related company policy where it applies. Do not invent policy terms,
timelines, refunds, credits, or guarantees that are not supported by the policy.

TASK:
1. Adapt retrieved strategies and visual evidence into a single, cohesive resolution strategy.
2. Draft an empathetic, precise, and actionable response for customer delivery.
3. Assign final escalation risk level (low, medium, high) and the matching notebook intent category.
4. Analyze the customer signal using the existing conversation history and return sentiment, sentiment_score (1-5), urgency, urgency_score (1-5), customer_intent, key_issue, and recommended_next_step.

Use only these labels: sentiment = negative, neutral, positive; intent = cancellation, refund, purchase, technical_issue, feedback, complaint, query; urgency = low, medium, high; escalation risk = low, medium, high.

Return JSON format with exact keys:
- "selected_category": string
- "matched_case_ids": list of strings
- "synthesized_strategy": string
- "drafted_response": string
- "escalation_risk": string
- "sentiment": string
- "sentiment_score": number
- "urgency": string
- "urgency_score": number
- "customer_intent": string
- "key_issue": string
- "recommended_next_step": string
"""

        try:
            response = None
            for attempt in range(3):
                try:
                    response = self.client.models.generate_content(
                        model=self.model,
                        contents=synthesis_prompt,
                        config=types.GenerateContentConfig(
                            response_mime_type="application/json",
                            temperature=0.2
                        )
                    )
                    break
                except Exception as error:
                    if attempt == 2 or "503" not in str(error):
                        raise
                    time.sleep(2 ** attempt)
            parsed_output = normalize_analysis(json.loads(response.text), user_query, similar_cases)
        except json.JSONDecodeError:
            parsed_output = analyze_customer_signal(user_query, similar_cases)
        except Exception as e:
            if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                parsed_output = analyze_customer_signal(user_query, similar_cases)
            else:
                raise HTTPException(status_code=500, detail=f"Gemini API Error: {str(e)}")

        parsed_output["detected_language"] = detected_language
        parsed_output.update(cbr_tracking)
        parsed_output["related_policy"] = policy_context

        hf_analysis = self.nlp.analyze(user_query)
        if hf_analysis:
            parsed_output["sentiment"] = hf_analysis.get("sentiment", parsed_output.get("sentiment", "neutral"))
            parsed_output["sentiment_score"] = hf_analysis.get("sentiment_score", parsed_output.get("sentiment_score", 3))
            parsed_output["customer_intent"] = hf_analysis.get("customer_intent", parsed_output.get("customer_intent", "query"))
            parsed_output["selected_category"] = parsed_output["customer_intent"]

        if parsed_output.get("analysis_source") == "local fallback (Gemini quota unavailable)":
            parsed_output["drafted_response"] = customer_response_fallback(detected_language, conversation_state)
        elif not parsed_output.get("drafted_response"):
            parsed_output["drafted_response"] = customer_response_fallback(detected_language, conversation_state)

        coaching_feedback = generate_coaching_feedback(
            parsed_output.get("drafted_response", ""),
            user_query,
        )
        parsed_output["feedback"] = asdict(coaching_feedback)
        parsed_output["coaching_tip"] = coaching_feedback.coaching_tip
        parsed_output["tone_score"] = coaching_feedback.tone_score
        parsed_output["empathy_score"] = coaching_feedback.empathy_score
        parsed_output["clarity_score"] = coaching_feedback.clarity_score

        if persist_case:
            support_case = self.case_registry.record_customer_message(
                customer_id=customer_id,
                case_id=case_id,
                query=user_query,
                analysis=parsed_output
            )
        else:
            support_case = self.case_registry.get_case(customer_id, case_id)

        if persist_case and customer_id and case_id:
            self.record_event(
                case_id=case_id,
                actor_type="ai_assistant",
                event_type="AI_ANALYSIS",
                event_details={"query": user_query, "analysis": parsed_output},
            )
            self.persist_message(
                case_id=case_id,
                sender_type="customer",
                message=user_query,
                language=detected_language,
            )
            drafted_response = parsed_output.get("drafted_response")
            if drafted_response:
                self.record_event(
                    case_id=case_id,
                    actor_type="ai_assistant",
                    event_type="AI_RECOMMENDATION",
                    event_details={"recommendation": drafted_response},
                )
                self.persist_message(
                    case_id=case_id,
                    sender_type="ai_assistant",
                    message=drafted_response,
                    language=detected_language,
                )
            if support_case is not None:
                parsed_output["department"] = support_case.get("department")
                parsed_output["routing_reason"] = support_case.get("routing_reason")
                support_case["messages"] = self.messages_for_case(case_id)

        return {
            "query": user_query,
            "customer_id": customer_id,
            "case_id": case_id,
            "language": detected_language,
            "support_case": support_case,
            "retrieved_cases": [
                case for case in retrieved_cases
                if float(case.get("normalized_similarity", 0) or 0) >= self.cbr_similar_threshold
            ],
            "retrieved_policies": retrieved_policies,
            "final_cbr_output": parsed_output
        }

    @staticmethod
    def record_event(
        *,
        case_id: str,
        actor_type: str,
        event_type: str,
        actor_id: Optional[int] = None,
        event_details: Optional[dict] = None,
    ) -> dict:
        with SessionLocal() as session:
            record = create_case_event_once(
                session,
                case_id=case_id,
                actor_type=actor_type,
                actor_id=actor_id,
                event_type=event_type,
                event_details=event_details,
            )
            return {
                "event_id": record.event_id,
                "case_id": record.case_id,
                "actor_type": record.actor_type,
                "actor_id": record.actor_id,
                "event_type": record.event_type,
                "event_details": record.event_details,
                "timestamp": record.timestamp.isoformat(),
            }

    @staticmethod
    def persist_message(
        *,
        case_id: str,
        sender_type: str,
        message: str,
        sender_id: Optional[int] = None,
        language: Optional[str] = None,
    ) -> dict:
        with SessionLocal() as session:
            existing = get_existing_message(
                session,
                case_id=case_id,
                sender_type=sender_type,
                message=message,
                sender_id=sender_id,
            )
            record = existing or add_message(
                session,
                case_id=case_id,
                sender_type=sender_type,
                sender_id=sender_id,
                message=message,
                language=language,
            )
            return {
                "message_id": record.message_id,
                "case_id": record.case_id,
                "sender_type": record.sender_type,
                "sender_id": record.sender_id,
                "message": record.message,
                "language": record.language,
                "timestamp": record.timestamp.isoformat(),
            }

    @staticmethod
    def messages_for_case(case_id: str) -> list[dict]:
        with SessionLocal() as session:
            return [
                {
                    "speaker": record.sender_type,
                    "text": record.message,
                    "timestamp": record.timestamp.isoformat(),
                }
                for record in get_case_messages(session, case_id)
            ]


class LazyPipelineProxy:
    """Defer expensive model, vector, and historical-case loading until first use."""

    def __init__(self):
        self._pipeline: CBRSystemPipeline | None = None
        self._lock = Lock()

    def _get_pipeline(self) -> CBRSystemPipeline:
        if self._pipeline is None:
            with self._lock:
                if self._pipeline is None:
                    self._pipeline = CBRSystemPipeline()
        return self._pipeline

    def __getattr__(self, name):
        return getattr(self._get_pipeline(), name)


# Initialize FastAPI Application
app = FastAPI(title="AI Customer Support CBR Backend", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

pipeline = LazyPipelineProxy()
queue_registry = SupportCaseRegistry()


@app.get("/health")
def health_check():
    return {
        "status": "online",
        "system": "CBR Backend",
        "gemini_model": os.getenv("GEMINI_MODEL", "gemini-3.6-flash"),
    }


@app.post("/api/auth/login")
def login(payload: LoginRequest):
    username = payload.username.strip().lower()
    if not username or not payload.password.strip():
        raise HTTPException(status_code=400, detail="Email and password are required.")
    role = payload.role
    return {
        "access_token": _create_token(username, role),
        "token_type": "bearer",
        "user": {
            "username": username,
            "role": role,
            "display_name": username.split("@", 1)[0],
        },
    }


@app.get("/api/auth/me")
def get_me(current_user: dict = Depends(get_current_user)):
    return current_user


@app.post("/api/tickets/process-text")
def process_text_ticket(payload: TextTicketRequest, current_user: dict = Depends(get_current_user)):
    if not payload.query.strip():
        raise HTTPException(status_code=400, detail="Query text cannot be empty.")
    return pipeline.process_ticket(
        user_query=payload.query,
        customer_id=payload.customer_id,
        case_id=payload.case_id,
        language=payload.language,
    )


@app.post("/api/cases/{customer_id}/{case_id}/use-historical-case")
def use_historical_case(
    customer_id: str,
    case_id: str,
    payload: HistoricalCaseUseRequest,
    current_user: dict = Depends(get_current_user),
):
    with SessionLocal() as session:
        current_case = get_case(session, case_id)
        if current_case is None or current_case.customer_id != customer_id:
            raise HTTPException(status_code=404, detail="Support case not found.")
        existing_analysis = {
            "intent": current_case.intent,
            "sentiment": current_case.sentiment,
            "urgency": current_case.urgency,
            "escalation_risk": current_case.escalation_risk,
            "key_issue": current_case.key_issue,
            "department": current_case.department,
        }
        customer_messages = [
            message.message
            for message in get_case_messages(session, case_id)
            if message.sender_type == "customer"
        ]

    if not customer_messages:
        raise HTTPException(status_code=409, detail="The current case has no customer message to adapt.")

    historical_case = pipeline.vector_db.get_case_for_llm(payload.historical_case_id)
    if historical_case is None:
        raise HTTPException(status_code=404, detail="Historical CBR case not found.")

    return pipeline.process_ticket(
        user_query=customer_messages[-1],
        customer_id=customer_id,
        case_id=case_id,
        language=detect_customer_language(customer_messages[-1]),
        selected_historical_case=historical_case,
        persist_case=False,
        existing_analysis=existing_analysis,
    )


@app.get("/api/cases/{customer_id}/{case_id}")
def get_support_case(customer_id: str, case_id: str, current_user: dict = Depends(get_current_user)):
    support_case = pipeline.case_registry.get_case(customer_id, case_id)
    if support_case is None:
        raise HTTPException(status_code=404, detail="Support case not found.")
    support_case = add_assignment_details(support_case)
    support_case["messages"] = pipeline.messages_for_case(case_id)
    return support_case


@app.get("/api/cases/{customer_id}/{case_id}/analysis")
def get_stored_analysis(
    customer_id: str,
    case_id: str,
    current_user: dict = Depends(get_current_user),
):
    with SessionLocal() as session:
        stored_analysis = get_stored_case_analysis(
            session,
            customer_id=customer_id,
            case_id=case_id,
            include_messages=True,
        )
    if stored_analysis is None:
        raise HTTPException(status_code=404, detail="Support case not found.")
    return stored_analysis


@app.post("/api/cases/{customer_id}/{case_id}/escalate")
def escalate_support_case(
    customer_id: str,
    case_id: str,
    payload: CaseEscalationRequest,
    current_user: dict = Depends(get_current_user),
):
    actor_id = None
    with SessionLocal() as session:
        user = session.scalar(select(User).where(User.email == current_user["username"]))
        if user is not None:
            actor_id = user.user_id
    try:
        support_case = pipeline.case_registry.escalate_case(
            customer_id,
            case_id,
            reason=payload.reason,
            actor_id=actor_id,
            details=payload.details,
        )
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error))
    if support_case is None:
        raise HTTPException(status_code=404, detail="Support case not found.")
    return add_assignment_details(support_case)


@app.post("/api/cases/{customer_id}/{case_id}/summarize")
def summarize_support_case(
    customer_id: str,
    case_id: str,
    current_user: dict = Depends(get_current_user),
):
    return {"summary": pipeline.summarize_case(customer_id, case_id)}


@app.post("/api/cases/{customer_id}/{case_id}/summary")
def generate_case_summary(
    customer_id: str,
    case_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Generate a summary only when explicitly requested by the user."""
    return {
        "case_id": case_id,
        "summary": pipeline.summarize_case(customer_id, case_id),
    }


@app.get("/api/cases/{customer_id}/{case_id}/brief", response_model=CaseBriefResponse)
def get_case_brief(
    customer_id: str,
    case_id: str,
    current_user: dict = Depends(get_current_user),
):
    return pipeline.case_brief(customer_id, case_id)


def add_assignment_details(support_case: dict) -> dict:
    with SessionLocal() as session:
        case = session.get(SupportCaseModel, support_case["case_id"])
        assigned_agent = session.get(User, case.assigned_agent_id) if case and case.assigned_agent_id else None
        support_case["department"] = case.department if case else None
        support_case["assigned_agent_id"] = case.assigned_agent_id if case else None
        support_case["assigned_agent"] = (
            {
                "user_id": assigned_agent.user_id,
                "name": assigned_agent.name,
                "email": assigned_agent.email,
            }
            if assigned_agent
            else None
        )
    return support_case


@app.post("/api/cases/{customer_id}/{case_id}/assign")
def assign_case_agent(
    customer_id: str,
    case_id: str,
    payload: CaseAssignmentRequest,
    current_user: dict = Depends(get_current_user),
):
    with SessionLocal() as session:
        existing_case = get_case(session, case_id)
        if existing_case is None or existing_case.customer_id != customer_id:
            raise HTTPException(status_code=404, detail="Support case not found.")
        if existing_case.assigned_agent_id == payload.agent_id:
            return add_assignment_details(pipeline.case_registry.get_case(customer_id, case_id))
    support_case = pipeline.case_registry.assign_agent(customer_id, case_id, payload.agent_id)
    if support_case is None:
        raise HTTPException(status_code=404, detail="Support case not found.")
    return add_assignment_details(support_case)


@app.post("/api/cases/{customer_id}/{case_id}/transfer")
def transfer_case_department(
    customer_id: str,
    case_id: str,
    payload: CaseDepartmentTransferRequest,
    current_user: dict = Depends(get_current_user),
):
    departments = {"support": "Support", "accounts": "Accounts"}
    new_department = departments.get(payload.department.strip().lower())
    if new_department is None:
        raise HTTPException(status_code=400, detail="Department must be Support or Accounts.")

    with SessionLocal() as session:
        case = get_case(session, case_id)
        if case is None or case.customer_id != customer_id:
            raise HTTPException(status_code=404, detail="Support case not found.")
        previous_department = case.department or "Support"
        if previous_department.lower() == new_department.lower():
            return add_assignment_details(pipeline.case_registry.get_case(customer_id, case_id))
        updated_case = update_case(session, case_id, department=new_department)

    actor_id = None
    with SessionLocal() as session:
        user = session.scalar(select(User).where(User.email == current_user["username"]))
        if user is not None:
            actor_id = user.user_id
    pipeline.record_event(
        case_id=case_id,
        actor_type="human_agent",
        actor_id=actor_id,
        event_type="DEPARTMENT_TRANSFER",
        event_details={
            "previous_department": previous_department,
            "new_department": new_department,
            "actor": current_user["username"],
            "actor_id": actor_id,
        },
    )
    transferred_case = pipeline.case_registry.get_case(customer_id, case_id)
    return add_assignment_details(transferred_case)


@app.post("/api/cases/{customer_id}/{case_id}/messages")
def add_case_message(
    customer_id: str,
    case_id: str,
    payload: CaseMessageRequest,
    current_user: dict = Depends(get_current_user),
):
    support_case = pipeline.case_registry.get_case(customer_id, case_id)
    if support_case is None:
        raise HTTPException(status_code=404, detail="Support case not found.")
    if not payload.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty.")
    sender_id = None
    with SessionLocal() as session:
        user = session.scalar(select(User).where(User.email == current_user["username"]))
        if user is not None:
            sender_id = user.user_id
    message = pipeline.persist_message(
        case_id=case_id,
        sender_type="human_agent",
        sender_id=sender_id,
        message=payload.message,
        language=payload.language,
    )
    with SessionLocal() as session:
        record_first_response(session, case_id)
    pipeline.record_event(
        case_id=case_id,
        actor_type="human_agent",
        actor_id=sender_id,
        event_type="AGENT_RESPONSE",
        event_details={"message_id": message["message_id"]},
    )
    return {"message": message, "messages": pipeline.messages_for_case(case_id)}


@app.post("/api/cases/{customer_id}/{case_id}/events")
def add_case_event(
    customer_id: str,
    case_id: str,
    payload: CaseEventRequest,
    current_user: dict = Depends(get_current_user),
):
    supported_event_types = {
        "AI_RECOMMENDATION_USED",
        "AI_RECOMMENDATION_REJECTED",
        "CASE_ESCALATED",
        "DEPARTMENT_TRANSFER",
    }
    if payload.event_type not in supported_event_types:
        raise HTTPException(status_code=400, detail="Unsupported event type.")
    if pipeline.case_registry.get_case(customer_id, case_id) is None:
        raise HTTPException(status_code=404, detail="Support case not found.")
    actor_id = None
    with SessionLocal() as session:
        user = session.scalar(select(User).where(User.email == current_user["username"]))
        if user is not None:
            actor_id = user.user_id
        if payload.event_type == "CASE_ESCALATED":
            details = payload.event_details or {}
            case = get_case(session, case_id)
            if case is not None:
                update_case(
                    session,
                    case_id,
                    escalation_status="ESCALATED",
                    escalation_reason=details.get("reason") or "Not specified",
                    escalated_at=datetime.now(timezone.utc),
                    escalation_actor_id=actor_id,
                    ai_escalation=False,
                )
        elif payload.event_type == "AI_RECOMMENDATION_USED":
            update_case(session, case_id, ai_recommendation_used=True)
        elif payload.event_type == "AI_RECOMMENDATION_REJECTED":
            update_case(session, case_id, ai_recommendation_rejected=True)
    event = pipeline.record_event(
        case_id=case_id,
        actor_type="human_agent",
        actor_id=actor_id,
        event_type=payload.event_type,
        event_details=payload.event_details,
    )
    return {"event": event}


@app.get("/api/cases/{customer_id}/{case_id}/events")
def list_case_events(
    customer_id: str,
    case_id: str,
    event_type: Optional[str] = None,
    current_user: dict = Depends(get_current_user),
):
    if pipeline.case_registry.get_case(customer_id, case_id) is None:
        raise HTTPException(status_code=404, detail="Support case not found.")
    with SessionLocal() as session:
        events = get_case_events(session, case_id, event_type=event_type)
        return {
            "events": [
                {
                    "event_id": event.event_id,
                    "case_id": event.case_id,
                    "actor_type": event.actor_type,
                    "actor_id": event.actor_id,
                    "event_type": event.event_type,
                    "event_details": event.event_details,
                    "timestamp": event.timestamp.isoformat(),
                }
                for event in events
            ]
        }


@app.get("/api/cases/active")
def list_active_support_cases(current_user: dict = Depends(get_current_user)):
    cases = queue_registry.list_active_cases()
    for support_case in cases:
        add_assignment_details(support_case)
        support_case["messages"] = pipeline.messages_for_case(support_case["case_id"])
    return {"cases": cases}


@app.patch("/api/cases/{customer_id}/{case_id}/status")
def update_support_case_status(
    customer_id: str,
    case_id: str,
    payload: CaseStatusUpdateRequest,
    current_user: dict = Depends(get_current_user),
):
    support_case = pipeline.case_registry.update_status(
        customer_id=customer_id,
        case_id=case_id,
        status=payload.status,
        resolution_summary=payload.resolution_summary,
    )
    if support_case is None:
        raise HTTPException(status_code=404, detail="Support case not found.")
    if payload.status == "RESOLVED":
        pipeline.ingest_resolved_case(case_id)
    return support_case


@app.post("/api/cases/add")
def add_case_to_vector_db(case_data: AddCaseRequest, current_user: dict = Depends(require_admin)):
    record = ComplaintRecord(**case_data.model_dump())
    pipeline.vector_db.add_record(record)
    return {"status": "success", "message": f"Case {case_data.case_id} indexed into Vector DB."}


@app.get("/api/admin/overview")
def admin_overview(current_user: dict = Depends(require_admin)):
    cases = list(pipeline.case_registry.cases.values())
    resolved_cases = [case for case in cases if case.status == "RESOLVED"]
    return {
        "total_cases": len(cases),
        "active_cases": len(cases) - len(resolved_cases),
        "resolved_cases": len(resolved_cases),
        "configured_roles": ["human_agent", "admin"],
    }


@app.get("/api/admin/escalations")
def admin_escalations(current_user: dict = Depends(require_admin)):
    escalations = []
    with SessionLocal() as session:
        cases = list_cases(session)
        for case in cases:
            if case.status == "RESOLVED":
                continue
            escalation_events = get_case_events(session, case.case_id, event_type="CASE_ESCALATED")
            latest_event = escalation_events[-1] if escalation_events else None
            if case.escalation_status != "ESCALATED" and latest_event is None:
                continue
            support_case = pipeline.case_registry.get_case(case.customer_id, case.case_id)
            priority = pipeline.case_registry.calculate_priority(
                pipeline.case_registry._to_support_case(case),
            )
            customer = session.get(Customer, case.customer_id)
            assigned_agent = session.get(User, case.assigned_agent_id) if case.assigned_agent_id else None
            event_details = latest_event.event_details if latest_event else {}
            escalated_at = case.escalated_at or (
                latest_event.timestamp if latest_event else None
            )
            escalations.append(
                {
                    "case_id": case.case_id,
                    "customer_id": case.customer_id,
                    "customer": {
                        "name": customer.name if customer else None,
                        "email": customer.email if customer else None,
                    },
                    "priority_score": priority["priority_score"],
                    "priority_label": priority["priority_label"],
                    "intent": case.intent,
                    "sentiment": case.sentiment,
                    "urgency": case.urgency,
                    "escalation_risk": case.escalation_risk,
                    "key_issue": case.key_issue,
                    "routing_reason": case.routing_reason,
                    "department": case.department,
                    "assigned_agent": (
                        {"user_id": assigned_agent.user_id, "name": assigned_agent.name, "email": assigned_agent.email}
                        if assigned_agent else None
                    ),
                    "escalation_reason": case.escalation_reason or event_details.get("reason"),
                    "escalated_by": latest_event.actor_id if latest_event else case.escalation_actor_id,
                    "escalated_at": escalated_at.isoformat() if escalated_at else None,
                    "created_at": case.created_at.isoformat(),
                    "status": case.status,
                    "analysis": (support_case or {}).get("latest_analysis") if support_case else None,
                }
            )
    escalations.sort(key=lambda item: (-item["priority_score"], item["created_at"]))
    return {"cases": escalations}


@app.get("/api/admin/agent-performance")
def admin_agent_performance(current_user: dict = Depends(require_admin)):
    return {"demo": True, "agents": [dict(agent) for agent in DEMO_AGENT_PERFORMANCE]}


@app.get("/api/admin/agents/{agent_id}/cases")
def admin_agent_cases(agent_id: str, current_user: dict = Depends(require_admin)):
    if agent_id not in DEMO_AGENT_CASES:
        raise HTTPException(status_code=404, detail="Demo agent not found.")
    return {
        "demo": True,
        "agent_id": agent_id,
        "cases": [dict(case) for case in DEMO_AGENT_CASES[agent_id]],
    }


@app.get("/api/admin/notifications")
def admin_notifications(current_user: dict = Depends(require_admin)):
    escalation_data = admin_escalations(current_user)
    notifications = []
    for case in escalation_data["cases"]:
        assigned_agent = case.get("assigned_agent") or {}
        agent_name = assigned_agent.get("name") or "the assigned agent"
        customer = case.get("customer") or {}
        notifications.append(
            {
                "type": "ESCALATION",
                "case_id": case["case_id"],
                "customer": customer.get("name") or case.get("customer_id"),
                "agent": agent_name,
                "department": case.get("department"),
                "message": f"Case {case['case_id']} was escalated by {agent_name}.",
                "priority": case.get("priority_label"),
                "reason": case.get("escalation_reason"),
                "escalated_at": case.get("escalated_at"),
            }
        )
    return {"notifications": notifications}


@app.get("/api/admin/analytics")
def admin_analytics(current_user: dict = Depends(require_admin)):
    with SessionLocal() as session:
        return overall_summary(session)


if __name__ == "__main__":
    import uvicorn
    # Updated module target to match your filename 'ai_cus_backend.py'
    uvicorn.run("ai_cus_backend:app", host="0.0.0.0", port=8000, reload=True)