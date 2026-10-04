"""
Manufacturing Stage 2: Model Scoring

Uses the trained AI4I 2020 Random Forest model.

Team pipeline contract:
    score(domain, record)

Returns:
    {
        "score": float,
        "reason_code": str,
        "factors": list[str],
        "model": str
    }

The ML score represents the estimated probability of machine failure.

Sensor warning conditions are also evaluated because predictive
maintenance should consider both model evidence and observable
sensor conditions.

RAG knowledge is retrieved from the Manufacturing maintenance
knowledge base using the detected sensor reason codes.
"""

import os

import joblib
import pandas as pd

from manufacturing.preprocessing import prepare_dataframe
from manufacturing.rag_retriever import retrieve_knowledge


_MODEL_PATH = os.path.join(
    os.path.dirname(__file__),
    "models",
    "manufacturing_ai4i_model.joblib",
)

_model = None


# ---------------------------------------------------------------------------
# Model loading
# ---------------------------------------------------------------------------

def _load_model():
    """Load the trained Manufacturing model once."""

    global _model

    if _model is None and os.path.exists(_MODEL_PATH):
        _model = joblib.load(_MODEL_PATH)

    return _model


# ---------------------------------------------------------------------------
# Sensor reasoning
# ---------------------------------------------------------------------------

def get_reason_codes(record: dict) -> list[str]:
    """
    Identify important sensor conditions.

    These thresholds are the validated rule-based sensor checks
    from the local Manufacturing MVP.
    """

    reasons = []

    if record.get("Tool wear", 0) >= 120:
        reasons.append("HIGH_TOOL_WEAR")

    if record.get("Torque", 0) >= 50:
        reasons.append("HIGH_TORQUE")

    if record.get("Process temperature", 0) >= 315:
        reasons.append("HIGH_PROCESS_TEMPERATURE")

    if record.get("Air temperature", 0) >= 305:
        reasons.append("HIGH_AIR_TEMPERATURE")

    if record.get("Rotational speed", 0) <= 1400:
        reasons.append("LOW_ROTATIONAL_SPEED")

    if (
        record.get("Rotational speed", 0) <= 1400
        and record.get("Torque", 0) >= 50
    ):
        reasons.append("HIGH_MECHANICAL_LOAD")

    if not reasons:
        reasons.append("NO_MAJOR_SENSOR_ANOMALY")

    return reasons


# ---------------------------------------------------------------------------
# ML risk
# ---------------------------------------------------------------------------

def get_ml_risk(probability: float) -> str:
    """
    Convert ML failure probability into a risk label.

    Thresholds selected from the local AI4I threshold analysis:
        < 0.15       LOW
        0.15 - <0.30 MEDIUM
        >= 0.30      HIGH
    """

    if probability >= 0.30:
        return "HIGH"

    if probability >= 0.15:
        return "MEDIUM"

    return "LOW"


# ---------------------------------------------------------------------------
# Sensor risk
# ---------------------------------------------------------------------------

def get_sensor_risk(reason_codes: list[str]) -> str:
    """Convert sensor warning count into a sensor risk level."""

    if reason_codes == ["NO_MAJOR_SENSOR_ANOMALY"]:
        return "LOW"

    warning_count = len(reason_codes)

    if warning_count >= 4:
        return "HIGH"

    if warning_count >= 2:
        return "MEDIUM"

    return "LOW"


# ---------------------------------------------------------------------------
# Overall risk
# ---------------------------------------------------------------------------

def _risk_rank(risk: str) -> int:
    return {
        "LOW": 1,
        "MEDIUM": 2,
        "HIGH": 3,
    }[risk]


def get_overall_risk(
    ml_risk: str,
    sensor_risk: str,
) -> str:
    """Use the more severe of ML and sensor risk."""

    if _risk_rank(sensor_risk) > _risk_rank(ml_risk):
        return sensor_risk

    return ml_risk


# ---------------------------------------------------------------------------
# Recommendation
# ---------------------------------------------------------------------------

def get_recommendation(overall_risk: str) -> str:
    """Return a maintenance recommendation."""

    if overall_risk == "HIGH":
        return "Urgent maintenance inspection recommended"

    if overall_risk == "MEDIUM":
        return "Schedule maintenance inspection"

    return "Continue monitoring machine"


# ---------------------------------------------------------------------------
# Model inference
# ---------------------------------------------------------------------------

def _predict_probability(record: dict) -> float:
    """Run the trained AI4I model."""

    model = _load_model()

    if model is None:
        raise FileNotFoundError(
            f"Manufacturing model not found: {_MODEL_PATH}"
        )

    input_df = pd.DataFrame([record])

    prepared_df = prepare_dataframe(input_df)

    feature_columns = [
        "Type",
        "Air temperature",
        "Process temperature",
        "Rotational speed",
        "Torque",
        "Tool wear",
    ]

    X = prepared_df[feature_columns]

    probability = float(
        model.predict_proba(X)[0][1]
    )

    return probability


# ---------------------------------------------------------------------------
# Deterministic fallback
# ---------------------------------------------------------------------------

def _fallback_score(record: dict) -> float:
    """
    Deterministic fallback when the trained model is unavailable.

    This is NOT a replacement for the trained model.
    It only keeps the pipeline operational.
    """

    score = 0.0

    if record.get("Tool wear", 0) >= 120:
        score += 0.20

    if record.get("Torque", 0) >= 50:
        score += 0.20

    if record.get("Process temperature", 0) >= 315:
        score += 0.15

    if record.get("Air temperature", 0) >= 305:
        score += 0.10

    if record.get("Rotational speed", 0) <= 1400:
        score += 0.15

    if (
        record.get("Rotational speed", 0) <= 1400
        and record.get("Torque", 0) >= 50
    ):
        score += 0.15

    return min(round(score, 4), 0.99)


# ---------------------------------------------------------------------------
# Public pipeline entrypoint
# ---------------------------------------------------------------------------

def score(domain: str, record: dict) -> dict:
    """
    Score one Manufacturing machine.

    The shared pipeline calls this function with:
        score("manufacturing", record)
    """

    if domain not in ("manufacturing", "sensor"):
        raise ValueError(
            f"Unsupported Manufacturing domain: {domain}"
        )

    reason_codes = get_reason_codes(record)

    try:
        probability = _predict_probability(record)

        model_name = "random_forest_ai4i"

    except Exception as exc:

        print(
            f"[Manufacturing ML scoring failed, "
            f"using deterministic fallback: {exc}]"
        )

        probability = _fallback_score(record)

        model_name = "heuristic_fallback"

    probability = round(probability, 4)

    ml_risk = get_ml_risk(probability)

    sensor_risk = get_sensor_risk(reason_codes)

    overall_risk = get_overall_risk(
        ml_risk,
        sensor_risk,
    )

    recommendation = get_recommendation(
        overall_risk
    )

    factors = [
        code
        for code in reason_codes
        if code != "NO_MAJOR_SENSOR_ANOMALY"
    ]

    if not factors:
        factors = [
            "no major sensor anomaly identified"
        ]

    # -----------------------------------------------------------------------
    # RAG knowledge retrieval
    # -----------------------------------------------------------------------
    try:
        knowledge_context = retrieve_knowledge(
            reason_codes
        )
    except Exception as exc:
        print(
            f"[Manufacturing RAG retrieval failed: {exc}]"
        )
        knowledge_context = ""

    return {
        "score": probability,
        "reason_code": (
            reason_codes[0]
            if reason_codes
            else "NO_MAJOR_SENSOR_ANOMALY"
        ),
        "factors": factors[:6],
        "model": model_name,
        "ml_risk": ml_risk,
        "sensor_risk": sensor_risk,
        "overall_risk": overall_risk,
        "reason_codes": reason_codes,
        "recommendation": recommendation,
        "model_version": "manufacturing-ai4i-v1",
        "knowledge_context": knowledge_context,
    }


# ---------------------------------------------------------------------------
# Local test
# ---------------------------------------------------------------------------

if __name__ == "__main__":

    test_machine = {
        "id": "M004",
        "machine_id": "M004",
        "Type": "L",
        "Air temperature": 310.0,
        "Process temperature": 320.0,
        "Rotational speed": 1350.0,
        "Torque": 60.0,
        "Tool wear": 180.0,
    }

    result = score(
        "manufacturing",
        test_machine,
    )

    print()
    print("=" * 80)
    print("MANUFACTURING MODEL SCORING TEST")
    print("=" * 80)

    for key, value in result.items():
        print(f"{key}: {value}")