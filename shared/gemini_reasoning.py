"""
Stage 3: Reasoning & Explanation
Converts a raw score into a plain-language explanation.

Calls Gemini if GOOGLE_API_KEY is set; otherwise falls back to a
templated mock explanation.

BFSI behavior is preserved.
Manufacturing support is added separately.
"""

import os

try:
    import google.generativeai as genai
except ImportError:
    genai = None


def _label(domain: str) -> str:
    """Return a human-readable label for the domain."""

    if domain == "loan":
        return "loan application"

    if domain in ("manufacturing", "sensor"):
        return "manufacturing machine"

    return "transaction"


def _mock_explain(domain: str, score_result: dict) -> str:
    """Create a local explanation when Gemini is unavailable."""

    # ---------------------------------------------------------
    # MANUFACTURING
    # ---------------------------------------------------------
    if domain in ("manufacturing", "sensor"):
        ml_score = score_result.get("score", 0)
        overall_risk = score_result.get(
            "overall_risk",
            "LOW",
        )

        reason_codes = (
            score_result.get("reason_codes")
            or score_result.get("factors")
            or []
        )

        factors_text = (
            ", ".join(reason_codes)
            if reason_codes
            else "no major sensor anomalies"
        )

        model_used = score_result.get(
            "model",
            "heuristic",
        )

        if model_used == "heuristic":
            caveat = (
                "This is a prototype rule-based estimate, "
                "not a trained model."
            )
        else:
            caveat = (
                f"Estimated by a trained model ({model_used}); "
                "this is a hackathon prototype, not a production "
                "decision system."
            )

        return (
            f"This machine has an ML risk score of {ml_score:.4f} "
            f"and an overall maintenance risk of {overall_risk}. "
            f"The main sensor factors are {factors_text}. "
            f"{caveat}"
        )

    # ---------------------------------------------------------
    # EXISTING BFSI LOGIC
    # ---------------------------------------------------------
    risk = round(score_result["score"] * 100)

    factors = score_result.get("factors") or []

    factors_text = (
        ", ".join(factors)
        if factors
        else "no major risk factors identified"
    )

    model_used = score_result.get(
        "model",
        "heuristic",
    )

    if model_used == "heuristic":
        caveat = (
            "This is a prototype rule-based estimate, "
            "not a trained model."
        )
    else:
        caveat = (
            f"Estimated by a trained model ({model_used}); "
            "this is a hackathon prototype, not a production "
            "decision system."
        )

    if domain == "loan":
        return (
            f"This loan is estimated at {risk}% default risk. "
            f"The main factors are {factors_text}. "
            f"{caveat}"
        )

    return (
        f"This transaction is estimated at {risk}% fraud risk. "
        f"The main signals are {factors_text}. "
        f"{caveat}"
    )


def explain(
    domain: str,
    record: dict,
    score_result: dict,
) -> str:
    """Return a plain-language explanation for a score result."""

    api_key = os.environ.get("GOOGLE_API_KEY")

    # ---------------------------------------------------------
    # LOCAL / MOCK FALLBACK
    # ---------------------------------------------------------
    if not api_key or genai is None:
        return (
            "[MOCK EXPLANATION - no GOOGLE_API_KEY set] "
            + _mock_explain(
                domain,
                score_result,
            )
        )

    try:
        genai.configure(api_key=api_key)

        model = genai.GenerativeModel(
            "gemini-1.5-flash"
        )

        # -----------------------------------------------------
        # MANUFACTURING GEMINI PROMPT + RAG
        # -----------------------------------------------------
        if domain in ("manufacturing", "sensor"):
            knowledge_context = score_result.get(
                "knowledge_context",
                "",
            )

            prompt = (
                "You are a predictive maintenance analyst "
                "assistant.\n\n"
                f"Given this manufacturing machine record: {record}\n\n"
                f"and this maintenance risk assessment: "
                f"{score_result}\n\n"
                "Use the following retrieved maintenance knowledge "
                "as the grounding source for your explanation:\n\n"
                f"{knowledge_context}\n\n"
                "Explain in 1-2 plain-language sentences why "
                "this machine received this risk level. "
                "Ground the explanation in the provided sensor "
                "factors, ML risk, and retrieved maintenance "
                "knowledge. Do not invent maintenance facts. "
                "Do not claim that the machine has definitely "
                "failed. Do not recommend automatically stopping "
                "machinery. Frame the result as maintenance "
                "decision support."
            )

        # -----------------------------------------------------
        # EXISTING BFSI GEMINI PROMPT
        # -----------------------------------------------------
        else:
            prompt = (
                f"You are a "
                f"{('loan risk' if domain == 'loan' else 'fraud')} "
                f"analyst assistant. "
                f"Given this {_label(domain)} record: {record}\n"
                f"and this risk score: {score_result}\n"
                f"Explain in 1-2 plain-language sentences why "
                f"this was scored this way. "
                f"Be concise and factual, no hedging."
            )

        response = model.generate_content(prompt)

        return response.text.strip()

    except Exception as e:
        # Fail gracefully to the mock explanation rather than
        # breaking the pipeline.
        return (
            f"[GEMINI CALL FAILED: {e}] "
            + _mock_explain(
                domain,
                score_result,
            )
        )