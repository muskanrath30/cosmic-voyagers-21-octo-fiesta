"""
Score every sample record (all assets) and write data/predictions.csv.

    python -m manufacturing.batch_predict            # with Gemini
    python -m manufacturing.batch_predict --no-llm   # fast, deterministic
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

if __package__ in (None, ""):  # allow `python batch_predict.py`
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd

from manufacturing import config, data_ingestion
from manufacturing.predict import predict_machine

OUTPUT_FILE = config.DATA_DIR / "predictions.csv"


def main() -> int:

    ap = argparse.ArgumentParser()
    ap.add_argument("--no-llm", action="store_true")
    args = ap.parse_args()

    print("=" * 80)
    print("MANUFACTURING BATCH PREDICTION")
    print("=" * 80)

    records = data_ingestion.list_all_records()
    print(f"\nRecords loaded: {len(records)}")

    rows = []
    for record in records:
        result = predict_machine(record, use_llm=not args.no_llm)
        rows.append({
            "id": result["machine_id"],
            "asset": result["asset"],
            "failure_probability": result["failure_probability"],
            "ml_risk": result["ml_risk"],
            "sensor_risk": result["sensor_risk"],
            "overall_risk": result["overall_risk"],
            "reason_codes": "|".join(result["reason_codes"]),
            "reasoning_source": result["reasoning_source"],
            "data_source": result["data_source"],
            "degraded": result["degraded"],
        })

    out = pd.DataFrame(rows)
    out.to_csv(OUTPUT_FILE, index=False)

    print(out.drop(columns=["reason_codes"]).to_string(index=False))
    print(f"\nSaved: {OUTPUT_FILE}")
    print("\nOverall risk counts:")
    print(out["overall_risk"].value_counts().to_string())
    return 0


if __name__ == "__main__":
    sys.exit(main())
