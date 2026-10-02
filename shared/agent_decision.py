"""
Stage 4: Decision & Action
Takes a score result and decides the next action.
Domain-aware: transactions get block/escalate/approve,
loan applications get deny/escalate/approve.
"""


def decide_action(domain: str, score_result: dict) -> str:
    """Decide the action for a record given its score result.

    domain: "loan" or "transaction"
    score_result: dict with at least a "score" key (0-1 float)
    """
    score = score_result["score"]

    if domain == "loan":
        if score >= 0.80:
            return "deny"
        if score >= 0.50:
            return "escalate"
        return "approve"

    # default: transaction domain
    if score >= 0.80:
        return "block"
    if score >= 0.50:
        return "escalate"
    return "approve"
