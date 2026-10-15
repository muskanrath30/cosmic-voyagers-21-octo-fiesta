"""
Threshold analysis for one asset.

    python -m manufacturing.threshold_analysis --asset machine_tool

Shows precision / recall / F1 at a range of thresholds on the VALIDATION split
(the split used to choose the operating threshold). The TEST split is shown
once at the chosen threshold, never used to pick it.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

if __package__ in (None, ""):  # allow `python threshold_analysis.py`
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import joblib
from sklearn.metrics import f1_score, precision_score, recall_score

from manufacturing import datasets
from manufacturing.train import (
    THRESHOLD_GRID,
    load_metrics,
    model_path,
    split_frame,
)


def main() -> int:

    ap = argparse.ArgumentParser()
    ap.add_argument("--asset", default="machine_tool", choices=list(datasets.ASSETS))
    args = ap.parse_args()

    asset = args.asset
    spec = datasets.get_spec(asset)

    if not model_path(asset).exists():
        sys.exit(f"No trained model for {asset}. Run: python -m manufacturing.train --asset {asset}")

    df = datasets.load_training_frame(asset).reset_index(drop=True)
    _, va, te, split_kind = split_frame(asset, df)
    model = joblib.load(model_path(asset))
    y = df[spec["target"]].astype(int)

    print("=" * 80)
    print(f"THRESHOLD ANALYSIS: {asset} (split: {split_kind})")
    print("=" * 80)

    val_probs = model.predict_proba(df.iloc[va][spec["features"]])[:, 1]
    print(f"\n{'threshold':>9} {'precision':>10} {'recall':>8} {'f1':>8} {'alerts':>8}   (validation)")
    for t in THRESHOLD_GRID:
        flags = (val_probs >= t).astype(int)
        print(f"{t:>9.2f} "
              f"{precision_score(y.iloc[va], flags, zero_division=0):>10.3f} "
              f"{recall_score(y.iloc[va], flags, zero_division=0):>8.3f} "
              f"{f1_score(y.iloc[va], flags, zero_division=0):>8.3f} "
              f"{int(flags.sum()):>8}")

    metrics = load_metrics(asset) or {}
    chosen = metrics.get("operating_threshold")
    if chosen is not None:
        test_probs = model.predict_proba(df.iloc[te][spec["features"]])[:, 1]
        flags = (test_probs >= chosen).astype(int)
        print(f"\nChosen on validation: {chosen}")
        print(f"Test at that threshold: "
              f"precision={precision_score(y.iloc[te], flags, zero_division=0):.3f} "
              f"recall={recall_score(y.iloc[te], flags, zero_division=0):.3f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
