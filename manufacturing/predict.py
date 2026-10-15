"""
Predict one record end to end (score + RAG + Gemini explanation).

    python -m manufacturing.predict                         # demo machine M004
    python -m manufacturing.predict --id TF-001             # a sample record
    python -m manufacturing.predict --id M004 --no-llm

predict_machine(record) keeps the original result shape (machine_id,
failure_probability, ...) and delegates all scoring to model_scoring.score, so
there is exactly one implementation of the scoring logic.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if __package__ in (None, ""):  # allow `python predict.py`
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from manufacturing import data_ingestion, gemini_reasoning, model_scoring


def predict_machine(record: dict, use_llm: bool = True) -> dict:
    """Run predictive-maintenance inference for one record."""

    scored = model_scoring.score("manufacturing", record)

    prediction = {
        "machine_id": scored["id"],
        "asset": scored["asset"],
        "failure_probability": scored["score"],
        "ml_risk": scored["ml_risk"],
        "sensor_warning_count": len(
            [c for c in scored["reason_codes"] if c != "NO_MAJOR_SENSOR_ANOMALY"]),
        "sensor_risk": scored["sensor_risk"],
        "overall_risk": scored["overall_risk"],
        "reason_codes": scored["reason_codes"],
        "recommendation": scored["recommendation"],
        "model_version": scored["model_version"],
        "data_source": scored["data_source"],
        "degraded": scored["degraded"],
        "knowledge_sources": scored["knowledge_sources"],
    }
    if "rul_cycles" in scored:
        prediction["rul_cycles"] = scored["rul_cycles"]

    if use_llm:
        explanation, source = gemini_reasoning.generate_explanation(scored)
    else:
        explanation = gemini_reasoning.get_fallback_explanation(scored)
        source = "LOCAL_FALLBACK"

    prediction["explanation"] = explanation
    prediction["reasoning_source"] = source
    return prediction


if __name__ == "__main__":

    ap = argparse.ArgumentParser()
    ap.add_argument("--id", default="M004", help="sample record id")
    ap.add_argument("--no-llm", action="store_true")
    args = ap.parse_args()

    record = data_ingestion.get_record("manufacturing", args.id)
    if record is None:
        sys.exit(f"Unknown record id: {args.id}")

    result = predict_machine(record, use_llm=not args.no_llm)

    print("=" * 80)
    print("MANUFACTURING PREDICTION")
    print("=" * 80)
    print(json.dumps(result, indent=2, default=str))
