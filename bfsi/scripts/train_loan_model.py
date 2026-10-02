"""
Trains the real Vehicle Loan Default risk model (replacing the heuristic scorer).

IMPORTANT: run scripts/inspect_loan_columns.py first to confirm your CSV's
columns match what this script expects (standard L&T Vehicle Loan Default
Prediction schema). If the target column isn't 'loan_default', pass
--target with the correct name.

Run locally:
    python scripts/train_loan_model.py --input data/vehicle_loan.csv

Saves:
    models/loan_model.joblib
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
from bfsi.feature_engineering import engineer_loan_dataframe, LOAN_FEATURE_COLUMNS


def main(input_path: str, output_path: str, target_col: str):
    print(f"Loading {input_path} ...")
    df = pd.read_csv(input_path)
    print(f"Loaded {len(df):,} rows, {len(df.columns)} columns")

    if target_col not in df.columns:
        raise ValueError(
            f"Target column '{target_col}' not found. "
            f"Run scripts/inspect_loan_columns.py first to find the right one, "
            f"then pass --target <name>. Columns present: {list(df.columns)}"
        )

    default_rate = df[target_col].mean() * 100
    print(f"Default rate: {default_rate:.2f}%")

    try:
        X = engineer_loan_dataframe(df)
    except KeyError as e:
        print(f"\nColumn mismatch: {e}")
        print("Run scripts/inspect_loan_columns.py to see your actual columns, "
              "then adjust shared/feature_engineering.py's engineer_loan_dataframe() "
              "to match -- paste me the column list and I'll fix it directly.")
        raise

    y = df[target_col]

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, stratify=y, random_state=42
    )
    print(f"Train: {len(X_train):,} rows | Test: {len(X_test):,} rows")

    neg, pos = (y_train == 0).sum(), (y_train == 1).sum()
    scale_pos_weight = neg / max(pos, 1)
    print(f"scale_pos_weight = {scale_pos_weight:.2f}")

    print("\n--- Baseline: Logistic Regression ---")
    baseline = LogisticRegression(class_weight="balanced", max_iter=1000)
    baseline.fit(X_train, y_train)
    baseline_proba = baseline.predict_proba(X_test)[:, 1]
    print(classification_report(y_test, baseline_proba >= 0.5, digits=3))
    print(f"ROC-AUC: {roc_auc_score(y_test, baseline_proba):.4f}")
    print(f"PR-AUC:  {average_precision_score(y_test, baseline_proba):.4f}")

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

    joblib.dump(model, output_path)
    with open(output_path.replace(".joblib", "_features.json"), "w") as f:
        json.dump(LOAN_FEATURE_COLUMNS, f)
    print(f"\nSaved model to {output_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="bfsi/data/vehicle_loan.csv")
    parser.add_argument("--output", default="bfsi/models/loan_model.joblib")
    parser.add_argument("--target", default="LOAN_DEFAULT")
    args = parser.parse_args()
    main(args.input, args.output, args.target)
