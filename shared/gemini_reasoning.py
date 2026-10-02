"""
Stage 3: Reasoning & Explanation
Converts a raw score into a plain-language explanation.
Calls Gemini if GOOGLE_API_KEY is set; otherwise falls back to a
templated mock explanation (matches the Hatchable prototype's current
behaviour, which is also templated, not yet calling an LLM).
"""
import os

try:
    import google.generativeai as genai
except ImportError:
    genai = None


def _label(domain: str) -> str:
    return "loan application" if domain == "loan" else "transaction"


def _mock_explain(domain: str, score_result: dict) -> str:
    risk = round(score_result["score"] * 100)
    factors = score_result.get("factors") or []
    factors_text = ", ".join(factors) if factors else "no major risk factors identified"

    model_used = score_result.get("model", "heuristic")
    if model_used == "heuristic":
        caveat = "This is a prototype rule-based estimate, not a trained model."
    else:
        caveat = f"Estimated by a trained model ({model_used}); this is a hackathon prototype, not a production decision system."

    if domain == "loan":
        return f"This loan is estimated at {risk}% default risk. The main factors are {factors_text}. {caveat}"
    return f"This transaction is estimated at {risk}% fraud risk. The main signals are {factors_text}. {caveat}"


def explain(domain: str, record: dict, score_result: dict) -> str:
    """Return a plain-language explanation for a score result."""
    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key or genai is None:
        return f"[MOCK EXPLANATION - no GOOGLE_API_KEY set] {_mock_explain(domain, score_result)}"

    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("gemini-1.5-flash")
        prompt = (
            f"You are a {('loan risk' if domain == 'loan' else 'fraud')} analyst assistant. "
            f"Given this {_label(domain)} record: {record}\n"
            f"and this risk score: {score_result}\n"
            f"Explain in 1-2 plain-language sentences why this was scored this way. "
            f"Be concise and factual, no hedging."
        )
        response = model.generate_content(prompt)
        return response.text.strip()
    except Exception as e:
        # Fail gracefully to the mock explanation rather than breaking the pipeline
        return f"[GEMINI CALL FAILED: {e}] {_mock_explain(domain, score_result)}"
