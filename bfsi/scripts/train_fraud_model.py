"""
Trains the real PaySim fraud model (replacing the heuristic scorer).

Run locally:
    python scripts/train_fraud_model.py --input data/paysim.csv

Expects the standard PaySim columns:
    step, type, amount, nameOrig, oldbalanceOrg, newbalanceOrig,
    nameDest, oldbalanceDest, newbalanceDest, isFraud, isFlaggedFraud

Saves:
    models/fraud_model.joblib
"""
import argparse
import json
import sys

import joblib
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    average_precision_score,
    classification_report,
    roc_auc_score,
)
from sklearn.model_selection import train_test_split
from xgboost import XGBClassifier

sys.path.insert(0, ".")
from bfsi.feature_engineering import engineer_transaction_dataframe, FRAUD_FEATURE_COLUMNS


def main(input_path: str, output_path: str):
    print(f"Loading {input_path} ...")
    df = pd.read_csv(input_path)
    print(f"Loaded {len(df):,} rows")

    required_cols = {"step", "type", "amount", "oldbalanceOrg", "newbalanceOrig",
                      "oldbalanceDest", "newbalanceDest", "isFraud"}
    missing = required_cols - set(df.columns)
    if missing:
        raise ValueError(f"Missing expected PaySim columns: {missing}. "
                          f"Found columns: {list(df.columns)}")

    # Fraud only occurs in TRANSFER / CASH_OUT -- filter down (per EDA)
    df = df[df["type"].isin(["TRANSFER", "CASH_OUT"])].copy()
    print(f"Filtered to TRANSFER/CASH_OUT: {len(df):,} rows")

    fraud_rate = df["isFraud"].mean() * 100
    print(f"Fraud rate in filtered set: {fraud_rate:.3f}%")

    X = engineer_transaction_dataframe(df)
    y = df["isFraud"]

    # Stratified split preserves the fraud/non-fraud ratio in both sets
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, stratify=y, random_state=42
    )
    print(f"Train: {len(X_train):,} rows | Test: {len(X_test):,} rows")

    # Handle severe imbalance via scale_pos_weight rather than resampling
    neg, pos = (y_train == 0).sum(), (y_train == 1).sum()
    scale_pos_weight = neg / max(pos, 1)
    print(f"scale_pos_weight = {scale_pos_weight:.1f}")

    # Baseline, for comparison in your pitch deck
    print("\n--- Baseline: Logistic Regression ---")
    baseline = LogisticRegression(class_weight="balanced", max_iter=1000)
    baseline.fit(X_train, y_train)
    baseline_proba = baseline.predict_proba(X_test)[:, 1]
    print(classification_report(y_test, baseline_proba >= 0.5, digits=3))
    print(f"ROC-AUC: {roc_auc_score(y_test, baseline_proba):.4f}")
    print(f"PR-AUC:  {average_precision_score(y_test, baseline_proba):.4f}")

    # Main model
    print("\n--- Main model: XGBoost ---")
    model = XGBClassifier(
        n_estimators=300,
        max_depth=6,
        learning_rate=0.05,
        scale_pos_weight=scale_pos_weight,
        eval_metric="aucpr",
        use_label_encoder=False,
        random_state=42,
    )
    model.fit(X_train, y_train)
    proba = model.predict_proba(X_test)[:, 1]
    print(classification_report(y_test, proba >= 0.5, digits=3))
    print(f"ROC-AUC: {roc_auc_score(y_test, proba):.4f}")
    print(f"PR-AUC:  {average_precision_score(y_test, proba):.4f}")

    # Compare against PaySim's own naive isFlaggedFraud rule, if present
    if "isFlaggedFraud" in df.columns:
        flagged = df.loc[X_test.index, "isFlaggedFraud"] if "isFlaggedFraud" in df.columns else None
        if flagged is not None:
            print(f"\nPaySim's own isFlaggedFraud rule caught "
                  f"{flagged.sum()} of {y_test.sum()} actual fraud cases in the test set "
                  f"-- your model should catch meaningfully more.")

    joblib.dump(model, output_path)
    with open(output_path.replace(".joblib", "_features.json"), "w") as f:
        json.dump(FRAUD_FEATURE_COLUMNS, f)
    print(f"\nSaved model to {output_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="bfsi/data/paysim.csv")
    parser.add_argument("--output", default="bfsi/models/fraud_model.joblib")
    args = parser.parse_args()
    main(args.input, args.output)
