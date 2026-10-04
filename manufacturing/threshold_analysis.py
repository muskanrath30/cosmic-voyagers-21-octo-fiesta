from pathlib import Path

import joblib
import pandas as pd

from sklearn.metrics import (
    precision_score,
    recall_score,
    f1_score,
)
from sklearn.model_selection import train_test_split

from preprocessing import (
    NUMERIC_FEATURES,
    CATEGORICAL_FEATURES,
    TARGET,
    prepare_dataframe,
)


ROOT = Path(__file__).resolve().parent

DATA_FILE = ROOT / "data" / "ai4i2020.csv"
MODEL_FILE = ROOT / "model" / "manufacturing_ai4i_model.joblib"


def main():

    print("=" * 80)
    print("MANUFACTURING FAILURE THRESHOLD ANALYSIS")
    print("=" * 80)

    # Load data
    df = pd.read_csv(DATA_FILE)

    df = prepare_dataframe(df)

    X = df[NUMERIC_FEATURES + CATEGORICAL_FEATURES]
    y = df[TARGET]

    # Reproduce the same test split used during training
    X_train, X_test, y_train, y_test = train_test_split(
        X,
        y,
        test_size=0.20,
        random_state=42,
        stratify=y,
    )

    # Load trained model
    model = joblib.load(MODEL_FILE)

    # Get probability of failure
    probabilities = model.predict_proba(X_test)[:, 1]

    print()
    print(f"Test records: {len(X_test)}")
    print(f"Actual failures: {int(y_test.sum())}")

    print()
    print(
        f"{'Threshold':<12}"
        f"{'Precision':<12}"
        f"{'Recall':<12}"
        f"{'F1':<12}"
        f"{'Detected':<12}"
    )

    print("-" * 60)

    thresholds = [
        0.05,
        0.10,
        0.15,
        0.20,
        0.25,
        0.30,
        0.35,
        0.40,
        0.45,
        0.50,
    ]

    for threshold in thresholds:

        predictions = (
            probabilities >= threshold
        ).astype(int)

        precision = precision_score(
            y_test,
            predictions,
            zero_division=0,
        )

        recall = recall_score(
            y_test,
            predictions,
            zero_division=0,
        )

        f1 = f1_score(
            y_test,
            predictions,
            zero_division=0,
        )

        detected = int(
            ((predictions == 1) & (y_test == 1)).sum()
        )

        print(
            f"{threshold:<12.2f}"
            f"{precision:<12.4f}"
            f"{recall:<12.4f}"
            f"{f1:<12.4f}"
            f"{detected:<12}"
        )


if __name__ == "__main__":
    main()