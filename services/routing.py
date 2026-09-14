from typing import Mapping


FINANCIAL_TERMS = (
    "refund",
    "failed refund",
    "payment",
    "billing",
    "duplicate charge",
    "charged twice",
    "incorrect charge",
    "wrong amount",
    "transaction",
    "money not received",
    "payment not received",
    "financial",
)


def determine_department(analysis: Mapping[str, object], query: str) -> tuple[str, str | None]:
    """Route using the existing analysis and message, without running new AI."""
    searchable_text = " ".join(
        str(analysis.get(field) or "")
        for field in ("customer_intent", "key_issue", "conversation_context")
    )
    searchable_text = f"{searchable_text} {query}".lower()
    intent = str(analysis.get("customer_intent") or "").lower()
    if intent in {"refund", "payment", "billing", "transaction"} or any(
        term in searchable_text for term in FINANCIAL_TERMS
    ):
        return "Accounts", "Financial/refund issue requiring Accounts verification."
    return "Support", None