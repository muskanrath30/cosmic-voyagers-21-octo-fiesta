"""
Manufacturing model training (all assets).

Usage (from the repository root):

    python -m manufacturing.train                    # every asset with data
    python -m manufacturing.train --asset turbofan_engine
    python -m manufacturing.train --asset machine_tool --beta 2

Also works as a plain script:  python train.py --asset bearing

Method
------
* 60 / 20 / 20 train / validation / test split.
* Rows from the same group never cross splits (C-MAPSS: engine; MetroPT-3:
  hour of operation; CWRU: source recording). This prevents the leakage that
  inflates scores when neighbouring cycles of one engine land in both train
  and test.
* The alert threshold is chosen on the VALIDATION split only. Test metrics are
  reported once, at that threshold.
* Test metrics are reported for ML-only, rules-only and the hybrid fusion.
* Healthy-row sensor bands for the reason-code rules come from the TRAIN split.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

if __package__ in (None, ""):  # allow `python train.py`
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from sklearn.metrics import (
    average_precision_score,
    confusion_matrix,
    fbeta_score,
    mean_absolute_error,
    mean_squared_error,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.model_selection import GroupShuffleSplit, train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

from manufacturing import config, datasets, risk_rules

log = config.get_logger("train")

SEED = 42
THRESHOLD_GRID = np.round(np.arange(0.05, 0.951, 0.05), 2)
HYBRID_EVAL_ROWS = 4000


# --------------------------------------------------------------------------- #
# Paths
# --------------------------------------------------------------------------- #
def model_path(asset: str) -> Path:
    return config.MODEL_DIR / f"{asset}_model.joblib"


def metrics_path(asset: str) -> Path:
    return config.MODEL_DIR / f"{asset}_metrics.json"


def bands_path(asset: str) -> Path:
    return config.MODEL_DIR / f"{asset}_bands.json"


def rul_path(asset: str) -> Path:
    return config.MODEL_DIR / f"{asset}_rul.joblib"


# --------------------------------------------------------------------------- #
# Splitting
# --------------------------------------------------------------------------- #
def _has_both_classes(y: pd.Series) -> bool:
    return y.nunique() > 1


def split_frame(asset: str, df: pd.DataFrame) -> tuple[np.ndarray, np.ndarray, np.ndarray, str]:
    """Return (train_idx, val_idx, test_idx, split_kind) as positional indices."""

    spec = datasets.get_spec(asset)
    y = df[spec["target"]].astype(int)
    group_col = spec["group"]
    idx = np.arange(len(df))

    if group_col and group_col in df.columns and df[group_col].nunique() >= 10:
        groups = df[group_col].astype(str).to_numpy()
        for attempt in range(25):
            seed = SEED + attempt
            outer = GroupShuffleSplit(n_splits=1, test_size=0.4, random_state=seed)
            train_idx, rest_idx = next(outer.split(idx, y, groups))
            inner = GroupShuffleSplit(n_splits=1, test_size=0.5, random_state=seed)
            v, t = next(inner.split(rest_idx, y.iloc[rest_idx], groups[rest_idx]))
            val_idx, test_idx = rest_idx[v], rest_idx[t]
            if all(_has_both_classes(y.iloc[i]) for i in (train_idx, val_idx, test_idx)):
                return train_idx, val_idx, test_idx, f"grouped_by_{group_col}"
        log.warning("grouped split could not balance classes; using stratified split")

    tr, rest = train_test_split(idx, test_size=0.4, random_state=SEED, stratify=y)
    va, te = train_test_split(rest, test_size=0.5, random_state=SEED,
                              stratify=y.iloc[rest])
    return tr, va, te, "stratified_random"


# --------------------------------------------------------------------------- #
# Model + helpers
# --------------------------------------------------------------------------- #
def build_estimator(asset: str):
    spec = datasets.get_spec(asset)
    clf = RandomForestClassifier(
        n_estimators=300, random_state=SEED, class_weight="balanced", n_jobs=-1
    )
    if spec["categorical"]:
        numeric = [f for f in spec["features"] if f not in spec["categorical"]]
        pre = ColumnTransformer([
            ("numeric", "passthrough", numeric),
            ("categorical", OneHotEncoder(handle_unknown="ignore"),
             spec["categorical"]),
        ])
        return Pipeline([("preprocessor", pre), ("classifier", clf)])
    return clf


def choose_threshold(y_true, probs, beta: float) -> float:
    """Pick the threshold with the best F-beta on the validation split."""

    best_t, best = 0.5, -1.0
    for t in THRESHOLD_GRID:
        score = fbeta_score(y_true, (probs >= t).astype(int), beta=beta,
                            zero_division=0)
        if score > best:
            best_t, best = float(t), score
    return best_t


def compute_bands(df: pd.DataFrame, spec: dict) -> dict:
    """Healthy-row normal bands (0.5..99.5 percentile) and medians."""

    healthy = df[df[spec["target"]] == 0]
    if len(healthy) < 50:
        healthy = df
    out = {}
    for f in spec["features"]:
        if f in spec["categorical"]:
            out[f] = {"mode": str(healthy[f].mode().iloc[0])}
            continue
        col = pd.to_numeric(healthy[f], errors="coerce").dropna()
        lo, hi = np.percentile(col, [0.5, 99.5])
        out[f] = {"lo": float(lo), "hi": float(hi), "median": float(col.median())}
    return out


def _rates(y_true, flags) -> dict:
    flags = np.asarray(flags).astype(int)
    return {
        "precision": float(precision_score(y_true, flags, zero_division=0)),
        "recall": float(recall_score(y_true, flags, zero_division=0)),
        "alerts": int(flags.sum()),
    }


def hybrid_comparison(asset, test_df, probs, threshold, bands) -> dict:
    """ML-only vs rules-only vs hybrid, all at the HIGH alert level."""

    spec = datasets.get_spec(asset)
    n = min(len(test_df), HYBRID_EVAL_ROWS)
    sel = np.random.default_rng(SEED).choice(len(test_df), n, replace=False)
    rows = test_df.iloc[sel]
    y = rows[spec["target"]].astype(int).to_numpy()
    p = np.asarray(probs)[sel]

    ml_flags, rule_flags, hybrid_flags = [], [], []
    for prob, (_, row) in zip(p, rows.iterrows()):
        record = row.to_dict()
        codes = risk_rules.get_reason_codes(asset, record, bands=_band_view(bands))
        ml = risk_rules.get_ml_risk(prob, threshold)
        sensor = risk_rules.get_sensor_risk(asset, codes)
        overall = risk_rules.get_overall_risk(ml, sensor)
        ml_flags.append(ml == "HIGH")
        rule_flags.append(sensor == "HIGH")
        hybrid_flags.append(overall == "HIGH")

    return {
        "rows_evaluated": int(n),
        "ml_only": _rates(y, ml_flags),
        "rules_only": _rates(y, rule_flags),
        "hybrid": _rates(y, hybrid_flags),
    }


def _band_view(bands: dict) -> dict:
    return {f: b for f, b in bands.items() if "lo" in b}


def nasa_score(y_true, y_pred) -> float:
    """NASA C-MAPSS asymmetric score: late predictions are penalised more."""

    d = np.asarray(y_pred) - np.asarray(y_true)
    return float(np.sum(np.where(d < 0, np.exp(-d / 13) - 1, np.exp(d / 10) - 1)))


# --------------------------------------------------------------------------- #
# Training
# --------------------------------------------------------------------------- #
def train_asset(asset: str, beta: float = 1.0) -> dict:
    spec = datasets.get_spec(asset)
    df = datasets.load_training_frame(asset).reset_index(drop=True)
    source = datasets.data_source(asset)
    feats, target = spec["features"], spec["target"]

    tr, va, te, split_kind = split_frame(asset, df)
    X = df[feats]
    y = df[target].astype(int)

    model = build_estimator(asset)
    model.fit(X.iloc[tr], y.iloc[tr])

    val_probs = model.predict_proba(X.iloc[va])[:, 1]
    threshold = choose_threshold(y.iloc[va], val_probs, beta)

    test_probs = model.predict_proba(X.iloc[te])[:, 1]
    flags = (test_probs >= threshold).astype(int)
    y_test = y.iloc[te]

    bands = compute_bands(df.iloc[tr], spec)
    comparison = hybrid_comparison(asset, df.iloc[te], test_probs, threshold, bands)

    metrics = {
        "asset": asset,
        "model": "RandomForestClassifier",
        "dataset": spec["dataset"],
        "data_source": source,
        "rows": int(len(df)),
        "split": split_kind,
        "split_rows": {"train": int(len(tr)), "validation": int(len(va)),
                       "test": int(len(te))},
        "features": feats,
        "positive_rate": float(y.mean()),
        "threshold_chosen_on": "validation",
        "threshold_beta": beta,
        "operating_threshold": float(threshold),
        "roc_auc": float(roc_auc_score(y_test, test_probs)) if _has_both_classes(y_test) else None,
        "pr_auc": float(average_precision_score(y_test, test_probs)) if _has_both_classes(y_test) else None,
        "precision": float(precision_score(y_test, flags, zero_division=0)),
        "recall": float(recall_score(y_test, flags, zero_division=0)),
        "f_beta": float(fbeta_score(y_test, flags, beta=beta, zero_division=0)),
        "confusion_matrix": confusion_matrix(y_test, flags, labels=[0, 1]).tolist(),
        "hybrid_comparison": comparison,
        "sklearn_version": sklearn.__version__,
        "trained_at": datetime.now(timezone.utc).isoformat(),
    }

    if asset == "turbofan_engine":
        metrics["rul"] = train_rul(df, feats, tr, te)

    config.MODEL_DIR.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, model_path(asset))
    bands_path(asset).write_text(
        json.dumps({"asset": asset, "features": bands}, indent=2), encoding="utf-8"
    )
    metrics_path(asset).write_text(json.dumps(metrics, indent=2), encoding="utf-8")

    log.info(f"trained {asset}", extra={"fields": {
        "asset": asset, "data_source": source, "threshold": threshold,
        "recall": metrics["recall"], "precision": metrics["precision"]}})
    return metrics


def train_rul(df, feats, tr, te) -> dict:
    """Remaining-useful-life regressor for the turbofan (capped RUL)."""

    reg = RandomForestRegressor(n_estimators=200, random_state=SEED, n_jobs=-1)
    reg.fit(df.iloc[tr][feats], df.iloc[tr]["rul"])
    pred = reg.predict(df.iloc[te][feats])
    true = df.iloc[te]["rul"]
    joblib.dump(reg, rul_path("turbofan_engine"))
    return {
        "rul_cap": datasets.CMAPSS_RUL_CAP,
        "rmse": float(np.sqrt(mean_squared_error(true, pred))),
        "mae": float(mean_absolute_error(true, pred)),
        "nasa_score": nasa_score(true, pred),
    }


def ensure_models() -> list[str]:
    """Train every asset that has data but no model yet (use at image build
    time or startup). Returns the assets trained."""

    trained = []
    for asset in datasets.ASSETS:
        if not model_path(asset).exists() and datasets.has_data(asset):
            train_asset(asset)
            trained.append(asset)
    return trained


def load_metrics(asset: str) -> dict | None:
    path = metrics_path(asset)
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def print_summary(m: dict) -> None:
    print(f"\n{'=' * 70}\n{m['asset']}  ({m['dataset']}, data: {m['data_source']})\n{'=' * 70}")
    print(f"rows={m['rows']}  split={m['split']}  threshold={m['operating_threshold']} (validation)")
    print(f"test precision={m['precision']:.3f} recall={m['recall']:.3f} "
          f"ROC-AUC={m['roc_auc']} PR-AUC={m['pr_auc']}")
    c = m["hybrid_comparison"]
    for name in ("ml_only", "rules_only", "hybrid"):
        r = c[name]
        print(f"  {name:<10} precision={r['precision']:.3f} recall={r['recall']:.3f} alerts={r['alerts']}")
    if "rul" in m:
        print(f"  RUL rmse={m['rul']['rmse']:.2f} nasa_score={m['rul']['nasa_score']:.0f}")
    if m["data_source"] == "synthetic_standin":
        print("  NOTE: synthetic stand-in data; run fetch_datasets.py for real data.")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--asset", default="all",
                    choices=["all", *datasets.ASSETS])
    ap.add_argument("--beta", type=float, default=1.0,
                    help="F-beta used to pick the threshold (2 favours recall)")
    args = ap.parse_args()

    assets = list(datasets.ASSETS) if args.asset == "all" else [args.asset]
    failed = 0
    for asset in assets:
        if not datasets.has_data(asset):
            print(f"[skip] {asset}: dataset not found (see download_dataset.py)")
            failed += args.asset != "all"
            continue
        print_summary(train_asset(asset, beta=args.beta))

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
