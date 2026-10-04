"""
Stage 4: Decision & Action

Domain-aware decision logic.

BFSI behavior is preserved:
    transaction -> block / escalate / approve
    loan        -> deny / escalate / approve

Manufacturing behavior:
    HIGH   -> urgent_maintenance_review
    MEDIUM -> schedule_maintenance
    LOW    -> continue_monitoring
"""


def decide_action(domain: str, score_result: dict) -> str:
    """
    Decide the next action based on domain and score.

    Existing BFSI behavior is intentionally unchanged.
    """

    # ---------------------------------------------------------
    # MANUFACTURING
    # ---------------------------------------------------------
    if domain in ("manufacturing", "sensor"):
        overall_risk = score_result.get(
            "overall_risk",
            "LOW",
        )

        if overall_risk == "HIGH":
            return "urgent_maintenance_review"

        if overall_risk == "MEDIUM":
            return "schedule_maintenance"

        return "continue_monitoring"

    # ---------------------------------------------------------
    # EXISTING BFSI: LOAN
    # ---------------------------------------------------------
    if domain == "loan":
        score = score_result["score"]

        if score >= 0.80:
            return "deny"

        if score >= 0.50:
            return "escalate"

        return "approve"

    # ---------------------------------------------------------
    # EXISTING BFSI: TRANSACTION
    # ---------------------------------------------------------
    score = score_result["score"]

    if score >= 0.80:
        return "block"

    if score >= 0.50:
        return "escalate"

    return "approve"