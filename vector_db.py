import os
import numpy as np
from dataclasses import dataclass, asdict
from typing import List, Dict, Any, Optional

from sentence_transformers import SentenceTransformer


# ============================================================
# CBR HISTORICAL CASE RECORD
# ============================================================

@dataclass
class ComplaintRecord:
    case_id: str
    category: str
    issue_description: str
    resolution_strategy: str
    recommended_reply: str
    escalation_risk: str
    success_rate: float

    # Existing fields kept for compatibility
    resolved: bool = True
    successfully_resolved: bool = True

    # Additional retrieval metadata
    intent: str = ""
    key_issue: str = ""
    context: str = ""
    department: str = ""


# ============================================================
# POLICY RECORD
# ============================================================

@dataclass
class PolicyRecord:
    policy_id: str
    topic: str
    source: str
    text: str


# ============================================================
# POLICY VECTOR ENGINE
# ============================================================

class PolicyVectorEngine:
    """
    Separate vector engine for company policy knowledge.

    IMPORTANT:
    Policy vectors are kept separate from historical CBR cases.

    Flow:

        Customer message
              ↓
        AI analysis
              ↓
        Policy query
              ↓
        PolicyVectorEngine
              ↓
        Relevant policy
              ↓
        Existing LLM synthesis
    """

    def __init__(
        self,
        model_name: str = "all-MiniLM-L6-v2",
        similarity_threshold: float = 0.35,
        encoder=None,
    ):
        from sentence_transformers import SentenceTransformer

        self.encoder = encoder or SentenceTransformer(model_name)

        self.records: List[PolicyRecord] = []

        embedding_dimension = int(
            self.encoder.get_embedding_dimension()
            if hasattr(self.encoder, "get_embedding_dimension")
            else self.encoder.get_sentence_embedding_dimension()
        )
        self.embeddings: np.ndarray = np.empty((0, embedding_dimension), dtype=np.float32)

        self.similarity_threshold = similarity_threshold

        self._populate_policy_knowledge_base()

    # --------------------------------------------------------
    # POLICY KNOWLEDGE BASE
    # --------------------------------------------------------

    def _populate_policy_knowledge_base(self) -> None:

        policies = [

            PolicyRecord(
                policy_id="POLICY-REFUNDS-01",
                topic="Refunds",
                source="InfiSupport Customer Service Policy",
                text=(
                    "For an approved refund, verify the order and payment "
                    "record. Submit the refund to the original payment "
                    "method. Communicate the expected processing timeline "
                    "clearly. Do not promise an instant bank credit. "
                    "Refund-related financial issues are handled by the "
                    "Accounts department."
                ),
            ),

            PolicyRecord(
                policy_id="POLICY-REFUND-DELAY-01",
                topic="Refund delays",
                source="InfiSupport Customer Service Policy",
                text=(
                    "When a customer reports that an approved refund has "
                    "not appeared, verify the refund status and original "
                    "payment transaction. Confirm whether the refund was "
                    "successfully submitted. Provide the expected bank "
                    "processing timeline and transaction reference when "
                    "available. Do not promise immediate credit. "
                    "Refund delays are routed to Accounts."
                ),
            ),

            PolicyRecord(
                policy_id="POLICY-RETURNS-01",
                topic="Returns",
                source="InfiSupport Customer Service Policy",
                text=(
                    "Confirm that the item is eligible for return. "
                    "Provide the supported return label or collection "
                    "option. Process the refund after the returned item "
                    "is received and checked. Return requests without "
                    "a payment or refund issue remain with Support."
                ),
            ),

            PolicyRecord(
                policy_id="POLICY-CANCELLATIONS-01",
                topic="Cancellations",
                source="InfiSupport Customer Service Policy",
                text=(
                    "Check the fulfillment status before cancelling an "
                    "order. If cancellation is eligible, confirm the "
                    "cancellation and explain the resulting process. "
                    "If the cancellation creates a refund or payment "
                    "issue, route the financial part to Accounts."
                ),
            ),

            PolicyRecord(
                policy_id="POLICY-BILLING-01",
                topic="Billing and payments",
                source="InfiSupport Customer Service Policy",
                text=(
                    "For billing or payment concerns, verify the "
                    "transaction and invoice details before discussing "
                    "an adjustment. Duplicate charges, incorrect charges, "
                    "pending transactions, failed payments involving a "
                    "debit, and payment discrepancies require Accounts "
                    "verification."
                ),
            ),

            PolicyRecord(
                policy_id="POLICY-DELIVERY-01",
                topic="Delivery",
                source="InfiSupport Customer Service Policy",
                text=(
                    "For delivery concerns, verify the order and tracking "
                    "information. Confirm the promised delivery date and "
                    "current carrier status. Provide the customer with "
                    "the next relevant update."
                ),
            ),

            PolicyRecord(
                policy_id="POLICY-DELIVERY-DELAY-01",
                topic="Delivery delays",
                source="InfiSupport Customer Service Policy",
                text=(
                    "For a delayed shipment, verify tracking and delivery "
                    "details. If the shipment is significantly delayed "
                    "or tracking has stopped, initiate the supported "
                    "carrier investigation. Provide the customer with "
                    "the next update and avoid promising an unsupported "
                    "delivery time."
                ),
            ),

            PolicyRecord(
                policy_id="POLICY-MISSING-DELIVERY-01",
                topic="Missing delivery",
                source="InfiSupport Customer Service Policy",
                text=(
                    "If tracking shows delivered but the customer cannot "
                    "locate the package, verify the delivery location "
                    "and carrier information. Check safe-drop details "
                    "where available and initiate a carrier investigation "
                    "when required."
                ),
            ),

            PolicyRecord(
                policy_id="POLICY-PRODUCT-01",
                topic="Damaged or defective products",
                source="InfiSupport Customer Service Policy",
                text=(
                    "For damaged or defective products, record the issue "
                    "clearly and request only the evidence required by "
                    "the support process. Follow the eligible replacement, "
                    "return, or warranty procedure."
                ),
            ),

            PolicyRecord(
                policy_id="POLICY-TECHNICAL-01",
                topic="Technical issues",
                source="InfiSupport Customer Service Policy",
                text=(
                    "For technical problems such as application errors, "
                    "checkout failures, crashes, synchronization problems, "
                    "or integration issues, identify the affected feature "
                    "and guide the customer through supported troubleshooting "
                    "steps. Escalate when the issue remains unresolved."
                ),
            ),

            PolicyRecord(
                policy_id="POLICY-ACCOUNT-01",
                topic="Account issues",
                source="InfiSupport Customer Service Policy",
                text=(
                    "For account access issues, verify the customer using "
                    "the supported recovery process. Use a secure recovery "
                    "or verification link. Never request or expose a "
                    "customer password."
                ),
            ),

            PolicyRecord(
                policy_id="POLICY-COMPLAINT-01",
                topic="Customer complaints",
                source="InfiSupport Customer Service Policy",
                text=(
                    "For customer complaints, acknowledge the concern, "
                    "review the case history, identify what remains "
                    "unresolved, and provide a clear next action. "
                    "Repeated unresolved complaints may require escalation."
                ),
            ),

            PolicyRecord(
                policy_id="POLICY-AGENT-CONDUCT-01",
                topic="Bad service or agent behavior",
                source="InfiSupport Customer Service Policy",
                text=(
                    "If a customer reports rude, inappropriate, dismissive, "
                    "or unprofessional agent behavior, acknowledge the "
                    "customer's concern and review the interaction. "
                    "Agent conduct complaints should be documented and "
                    "escalated according to the complaint process."
                ),
            ),

            PolicyRecord(
                policy_id="POLICY-ESCALATION-01",
                topic="Escalation and exceptions",
                source="InfiSupport Customer Service Policy",
                text=(
                    "Escalate when the issue remains unresolved, requires "
                    "manager intervention, involves a policy exception, "
                    "or requires another specialized team. Record the "
                    "reason for escalation and keep the customer informed "
                    "of the next owner or action."
                ),
            ),

            PolicyRecord(
                policy_id="POLICY-PRIORITY-01",
                topic="Priority handling",
                source="InfiSupport Customer Service Policy",
                text=(
                    "Priority should consider customer impact, urgency, "
                    "escalation risk, and waiting time. Older unresolved "
                    "cases should gain priority over time to avoid "
                    "starvation."
                ),
            ),

            PolicyRecord(
                policy_id="POLICY-COMMUNICATION-01",
                topic="Customer communication",
                source="InfiSupport Customer Service Policy",
                text=(
                    "Customer communication should be clear, concise, "
                    "empathetic, and accurate. Agents should not promise "
                    "actions or timelines that have not been verified. "
                    "For multilingual conversations, preserve the "
                    "customer's original meaning and respond in the "
                    "customer's language where supported."
                ),
            ),
        ]

        for policy in policies:
            self.add_record(policy)

    # --------------------------------------------------------
    # ADD POLICY
    # --------------------------------------------------------

    def add_record(self, record: PolicyRecord) -> None:

        vector = self.encoder.encode(
            [record.text],
            normalize_embeddings=True
        )[0]

        # Replace existing policy with same ID
        existing_index = next(
            (
                index
                for index, existing in enumerate(self.records)
                if existing.policy_id == record.policy_id
            ),
            None,
        )

        if existing_index is not None:

            self.records[existing_index] = record
            self.embeddings[existing_index] = vector

            return

        self.records.append(record)

        if self.embeddings.size == 0:
            self.embeddings = np.array([vector])
        else:
            self.embeddings = np.vstack(
                [self.embeddings, vector]
            )

    # --------------------------------------------------------
    # POLICY SEARCH
    # --------------------------------------------------------

    def search_relevant(
        self,
        query: str,
        top_k: int = 1
    ) -> List[Dict[str, Any]]:

        if not self.records:
            return []

        query_vec = self.encoder.encode(
            [query],
            normalize_embeddings=True
        )[0]

        # Since embeddings are normalized:
        # dot product = cosine similarity
        similarities = np.dot(
            self.embeddings,
            query_vec
        )

        query_lower = query.lower()

        topic_terms = {

            "Refunds": (
                "refund",
                "money back",
                "money not received",
                "refund status",
            ),
            "Refund delays": (
                "refund delayed",
                "refund pending",
                "refund not received",
                "waiting for refund",
                "refund taking",
            ),

            "Returns": (
                "return",
                "send back",
                "return label",
                "returned item",
            ),

            "Cancellations": (
                "cancel",
                "cancellation",
                "cancel order",
            ),

            "Delivery": (
                "delivery",
                "shipment",
                "parcel",
                "package",
                "tracking",
            ),

            "Delivery delays": (
                "delivery delayed",
                "late delivery",
                "shipment delayed",
                "stuck in transit",
                "tracking stopped",
                "delayed parcel",
            ),

            "Missing delivery": (
                "marked delivered",
                "not received",
                "missing package",
                "missing parcel",
                "delivered but",
            ),

            "Damaged or defective products": (
                "damaged",
                "defect",
                "broken",
                "faulty",
                "replacement",
                "warranty",
            ),

            "Billing and payments": (
                "billing",
                "payment",
                "charge",
                "charged",
                "transaction",
                "invoice",
                "debited",
            ),

            "Technical issues": (
                "technical",
                "error",
                "crash",
                "freeze",
                "app",
                "website",
                "api",
                "sync",
                "checkout",
            ),

            "Account issues": (
                "account",
                "login",
                "password",
                "access",
                "verification",
                "otp",
            ),

            "Customer complaints": (
                "complaint",
                "unresolved",
                "poor service",
                "bad service",
                "disappointed",
            ),

            "Bad service or agent behavior": (
                "rude",
                "unprofessional",
                "agent behavior",
                "agent was rude",
                "poor support",
            ),

            "Escalation and exceptions": (
                "escalate",
                "manager",
                "exception",
                "unresolved",
            ),

            "Priority handling": (
                "urgent",
                "priority",
                "waiting",
                "critical",
            ),

            "Customer communication": (
                "language",
                "communication",
                "explain",
                "translate",
            ),
        }

        scored_indices = []

        for idx, record in enumerate(self.records):

            topic_boost = 0.0

            matching_terms = topic_terms.get(
                record.topic,
                ()
            )

            if any(
                term in query_lower
                for term in matching_terms
            ):
                topic_boost = 0.10

            score = float(
                similarities[idx] + topic_boost
            )

            scored_indices.append(
                (score, idx)
            )

        # Highest score first
        scored_indices.sort(
            key=lambda x: x[0],
            reverse=True
        )

        results = []

        for score, idx in scored_indices:

            if score < self.similarity_threshold:
                continue

            record = asdict(
                self.records[idx]
            )

            record["similarity_score"] = round(
                score,
                4
            )

            record["similarity_percent"] = round(
                score * 100,
                1
            )

            results.append(record)

            if len(results) >= top_k:
                break

        return results


# ============================================================
# CBR VECTOR ENGINE
# ============================================================

class VectorCBREngine:
    """
    Case-Based Reasoning engine.

    Historical successful cases are converted into embeddings.

    Retrieval flow:

        Customer Message
              ↓
        AI Analysis
              ↓
        Query Representation
              ↓
        Sentence Transformer
              ↓
        Cosine Similarity
              ↓
        Threshold Filtering
              ↓
        Top 3 Similar Resolved Cases
    """

    def __init__(
        self,
        model_name: str = "all-MiniLM-L6-v2",
        similarity_threshold: float | None = None,
        encoder=None,
    ):
        from sentence_transformers import SentenceTransformer

        self.encoder = encoder or SentenceTransformer(model_name)

        self.records: List[ComplaintRecord] = []

        embedding_dimension = int(
            self.encoder.get_embedding_dimension()
            if hasattr(self.encoder, "get_embedding_dimension")
            else self.encoder.get_sentence_embedding_dimension()
        )
        self.embeddings: np.ndarray = np.empty(
            (0, embedding_dimension), dtype=np.float32
        )

        self.similarity_threshold = (
            float(os.getenv("CBR_SIMILAR_THRESHOLD", "0.40"))
            if similarity_threshold is None
            else similarity_threshold
        )

    # ========================================================
    # BUILD HISTORICAL CASE TEXT
    # ========================================================

    @staticmethod
    def build_record_text(
        record: ComplaintRecord
    ) -> str:
        """
        Build the semantic representation of a historical case.

        We intentionally do NOT include:
            - resolution_strategy
            - recommended_reply

        Those fields are used later when the agent selects
        "Use".

        Retrieval should answer:

            "Is this historical customer problem similar?"

        rather than:

            "Does this historical solution look similar?"
        """

        return f"""
Category:
{record.category}

Intent:
{record.intent}

Key Issue:
{record.key_issue}

Customer Issue:
{record.issue_description}

Context:
{record.context}

Department:
{record.department}
""".strip()

    # ========================================================
    # BUILD CURRENT CUSTOMER QUERY
    # ========================================================

    @staticmethod
    def build_query_text(
        customer_message: str,
        intent: str = "",
        key_issue: str = "",
        category: str = "",
        context: str = "",
        department: str = ""
    ) -> str:
        """
        Build semantic query using both the original customer
        message and normalized AI signals.

        The original message remains the most important source.
        AI signals help normalize different phrasings.
        """

        return f"""
Category:
{category}

Intent:
{intent}

Key Issue:
{key_issue}

Customer Message:
{customer_message}

Context:
{context}

Department:
{department}
""".strip()

    # ========================================================
    # ADD HISTORICAL CASE
    # ========================================================

    def add_record(
        self,
        record: ComplaintRecord
    ) -> None:
        """
        Add or replace a historical case.

        Only successfully resolved cases should become CBR
        knowledge.
        """

        if not record.resolved:
            return

        if not record.successfully_resolved:
            return

        text = self.build_record_text(
            record
        )

        vector = self.encoder.encode(
            [text],
            normalize_embeddings=True
        )[0]

        # ----------------------------------------------------
        # Replace if case ID already exists
        # ----------------------------------------------------

        existing_index = next(
            (
                index
                for index, existing
                in enumerate(self.records)
                if existing.case_id == record.case_id
            ),
            None,
        )

        if existing_index is not None:

            self.records[existing_index] = record
            self.embeddings[existing_index] = vector

            return

        # ----------------------------------------------------
        # Insert new record
        # ----------------------------------------------------

        self.records.append(record)

        if self.embeddings.size == 0:

            self.embeddings = np.array(
                [vector]
            )

        else:

            self.embeddings = np.vstack(
                [
                    self.embeddings,
                    vector
                ]
            )

    def add_records(self, records: List[ComplaintRecord]) -> None:
        """Batch-index resolved cases so startup performs one encoder call."""
        valid_records = [
            record for record in records
            if record.resolved and record.successfully_resolved
        ]
        if not valid_records:
            return

        texts = [self.build_record_text(record) for record in valid_records]
        vectors = self.encoder.encode(texts, normalize_embeddings=True, batch_size=32)
        self.records = valid_records
        self.embeddings = np.asarray(vectors, dtype=np.float32)

    # ========================================================
    # SEARCH SIMILAR CASES
    # ========================================================

    def search_similar(
        self,
        query: str,
        top_k: int = 3,
        threshold: Optional[float] = None
    ) -> List[Dict[str, Any]]:
        """
        Retrieve the most semantically similar successful
        historical cases.

        Similarity is cosine similarity.

        Default:
            top_k = 3
            threshold = configured engine threshold

        Weak matches below threshold are hidden.
        """

        if not self.records:
            return []

        if self.embeddings.size == 0:
            return []

        if threshold is None:
            threshold = self.similarity_threshold

        # ----------------------------------------------------
        # Encode query
        # ----------------------------------------------------

        query_vec = self.encoder.encode(
            [query],
            normalize_embeddings=True
        )[0]

        # ----------------------------------------------------
        # Cosine similarity
        #
        # Both database vectors and query vector are normalized.
        # Therefore:
        #
        # cosine_similarity = dot_product
        # ----------------------------------------------------

        similarities = np.dot(
            self.embeddings,
            query_vec
        )

        # ----------------------------------------------------
        # Rank highest similarity first
        # ----------------------------------------------------

        ranked_indices = np.argsort(
            similarities
        )[::-1]

        results = []

        for idx in ranked_indices:

            raw_score = float(
                similarities[idx]
            )

            # Hide weak recommendations
            if raw_score < threshold:
                continue

            record_dict = asdict(
                self.records[idx]
            )

            record_dict["raw_score"] = round(
                raw_score,
                4
            )

            record_dict["normalized_similarity"] = round(
                raw_score,
                4
            )

            record_dict["similarity_score"] = round(
                raw_score,
                4
            )

            record_dict["similarity_percent"] = round(
                raw_score * 100,
                1
            )

            results.append(
                record_dict
            )

            # We only need top 3
            if len(results) >= top_k:
                break

        return results

    # ========================================================
    # SEARCH USING STRUCTURED AI ANALYSIS
    # ========================================================

    def search_similar_cases(
        self,
        customer_message: str,
        intent: str = "",
        key_issue: str = "",
        category: str = "",
        context: str = "",
        department: str = "",
        top_k: int = 3
    ) -> List[Dict[str, Any]]:
        """
        Preferred search method for the application.

        Uses:
            original customer message
            +
            AI intent
            +
            key issue
            +
            category
            +
            context
            +
            department
        """

        query_text = self.build_query_text(
            customer_message=customer_message,
            intent=intent,
            key_issue=key_issue,
            category=category,
            context=context,
            department=department
        )

        return self.search_similar(
            query=query_text,
            top_k=top_k
        )

    # ========================================================
    # GET SELECTED CASE
    # ========================================================

    def get_case(
        self,
        case_id: str
    ) -> Optional[ComplaintRecord]:
        """
        Return a historical case by stable case ID.

        Used by the future "Use" button workflow.
        """

        for record in self.records:

            if record.case_id == case_id:
                return record

        return None

    # ========================================================
    # PREPARE CASE FOR LLM
    # ========================================================

    def get_case_for_llm(
        self,
        case_id: str
    ) -> Optional[Dict[str, Any]]:
        """
        Return the selected historical case information
        that can be passed to the existing LLM.

        The historical response is treated as a reference,
        NOT copied blindly.
        """

        record = self.get_case(
            case_id
        )

        if record is None:
            return None

        return {
            "case_id": record.case_id,
            "category": record.category,
            "intent": record.intent,
            "key_issue": record.key_issue,
            "customer_issue": record.issue_description,
            "issue_description": record.issue_description,
            "context": record.context,
            "department": record.department,
            "resolution_strategy": record.resolution_strategy,
            "successful_response": record.recommended_reply,
            "recommended_reply": record.recommended_reply,
            "escalation_risk": record.escalation_risk,
            "success_rate": record.success_rate,
            "resolved": record.resolved,
            "successfully_resolved": record.successfully_resolved,
        }


# ============================================================
# OPTIONAL HELPER
# ============================================================

def build_cbr_query(
    customer_message: str,
    analysis: Optional[Dict[str, Any]] = None,
    department: str = ""
) -> str:
    """
    Convenience helper for the existing backend.

    Example:

        query = build_cbr_query(
            customer_message,
            analysis,
            department
        )

        results = vector_db.search_similar(
            query,
            top_k=3
        )
    """

    analysis = analysis or {}

    return VectorCBREngine.build_query_text(
        customer_message=customer_message,
        intent=analysis.get(
            "customer_intent",
            ""
        ),
        key_issue=analysis.get(
            "key_issue",
            ""
        ),
        category=analysis.get(
            "selected_category",
            ""
        ),
        context=analysis.get(
            "conversation_context",
            analysis.get(
                "context",
                ""
            )
        ),
        department=department
    )