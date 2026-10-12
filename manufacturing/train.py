from pathlib import Path
import json

import joblib
import pandas as pd

from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

from preprocessing import (
    CATEGORICAL_FEATURES,
    NUMERIC_FEATURES,
    TARGET,
    prepare_dataframe,
)


ROOT = Path(__file__).resolve().parent

DATA_FILE = ROOT / "data" / "ai4i2020.csv"
MODEL_DIR = ROOT / "models"

MODEL_FILE = MODEL_DIR / "manufacturing_ai4i_model.joblib"
METRICS_FILE = MODEL_DIR / "metrics.json"


def main():

    print("=" * 70)
    print("MANUFACTURING PREDICTIVE MAINTENANCE MODEL TRAINING")
    print("=" * 70)

    # ---------------------------------------------------------
    # 1. Load dataset
    # ---------------------------------------------------------

    print("\n[1/7] Loading dataset...")

    df = pd.read_csv(DATA_FILE)

    print(f"Dataset shape: {df.shape}")

    # ---------------------------------------------------------
    # 2. Clean dataset
    # ---------------------------------------------------------

    print("\n[2/7] Preparing dataset...")

    df = prepare_dataframe(df)

    print(f"Shape after preprocessing: {df.shape}")

    # ---------------------------------------------------------
    # 3. Separate features and target
    # ---------------------------------------------------------

    print("\n[3/7] Separating features and target...")

    X = df[NUMERIC_FEATURES + CATEGORICAL_FEATURES]
    y = df[TARGET]

    print(f"Features: {list(X.columns)}")
    print(f"Target: {TARGET}")

    print("\nTarget distribution:")
    print(y.value_counts())

    # ---------------------------------------------------------
    # 4. Train/test split
    # ---------------------------------------------------------

    print("\n[4/7] Splitting dataset...")

    X_train, X_test, y_train, y_test = train_test_split(
        X,
        y,
        test_size=0.20,
        random_state=42,
        stratify=y,
    )

    print(f"Training records: {len(X_train)}")
    print(f"Testing records: {len(X_test)}")

    # ---------------------------------------------------------
    # 5. Build preprocessing + Random Forest pipeline
    # ---------------------------------------------------------

    print("\n[5/7] Building Random Forest model...")

    preprocessor = ColumnTransformer(
        transformers=[
            (
                "numeric",
                "passthrough",
                NUMERIC_FEATURES,
            ),
            (
                "categorical",
                OneHotEncoder(handle_unknown="ignore"),
                CATEGORICAL_FEATURES,
            ),
        ]
    )

    classifier = RandomForestClassifier(
        n_estimators=300,
        random_state=42,
        class_weight="balanced",
        n_jobs=-1,
    )

    model = Pipeline(
        steps=[
            (
                "preprocessor",
                preprocessor,
            ),
            (
                "classifier",
                classifier,
            ),
        ]
    )

    # ---------------------------------------------------------
    # 6. Train model
    # ---------------------------------------------------------

    print("\n[6/7] Training model...")

    model.fit(X_train, y_train)

    print("Training completed.")

    # ---------------------------------------------------------
    # 7. Evaluate model
    # ---------------------------------------------------------

    print("\n[7/7] Evaluating model...")

    predictions = model.predict(X_test)

    probabilities = model.predict_proba(X_test)[:, 1]

    accuracy = accuracy_score(
        y_test,
        predictions,
    )

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

    roc_auc = roc_auc_score(
        y_test,
        probabilities,
    )

    confusion = confusion_matrix(
        y_test,
        predictions,
    )

    report = classification_report(
        y_test,
        predictions,
        zero_division=0,
    )

    print("\n" + "=" * 70)
    print("MODEL RESULTS")
    print("=" * 70)

    print(f"Accuracy : {accuracy:.4f}")
    print(f"Precision: {precision:.4f}")
    print(f"Recall   : {recall:.4f}")
    print(f"F1 Score : {f1:.4f}")
    print(f"ROC-AUC  : {roc_auc:.4f}")

    print("\nConfusion Matrix:")
    print(confusion)

    print("\nClassification Report:")
    print(report)

    # ---------------------------------------------------------
    # Save model
    # ---------------------------------------------------------

    MODEL_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    joblib.dump(
        model,
        MODEL_FILE,
    )

    print(f"\nModel saved to:")
    print(MODEL_FILE)

    # ---------------------------------------------------------
    # Save metrics
    # ---------------------------------------------------------

    metrics = {
        "model": "RandomForestClassifier",
        "dataset": "AI4I 2020 Predictive Maintenance",
        "rows": int(len(df)),
        "features": NUMERIC_FEATURES + CATEGORICAL_FEATURES,
        "accuracy": float(accuracy),
        "precision": float(precision),
        "recall": float(recall),
        "f1_score": float(f1),
        "roc_auc": float(roc_auc),
        "confusion_matrix": confusion.tolist(),
    }

    with open(
        METRICS_FILE,
        "w",
        encoding="utf-8",
    ) as file:
        json.dump(
            metrics,
            file,
            indent=4,
        )

    print(f"Metrics saved to:")
    print(METRICS_FILE)

    print("\nTraining pipeline completed successfully.")


if __name__ == "__main__":
    main()
