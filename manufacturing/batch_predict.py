from pathlib import Path

import pandas as pd

from predict import predict_machine


ROOT = Path(__file__).resolve().parent

INPUT_FILE = ROOT / "data" / "machine_data.csv"
OUTPUT_FILE = ROOT / "data" / "predictions.csv"


def main():

    print("=" * 80)
    print("MANUFACTURING BATCH PREDICTION")
    print("=" * 80)

    # ---------------------------------------------------------
    # 1. Load machine data
    # ---------------------------------------------------------

    print("\n[1/4] Loading machine data...")

    dataframe = pd.read_csv(
        INPUT_FILE
    )

    print(
        f"Machines loaded: {len(dataframe)}"
    )

    # ---------------------------------------------------------
    # 2. Predict every machine
    # ---------------------------------------------------------

    print("\n[2/4] Running predictions...")

    results = []

    for _, row in dataframe.iterrows():

        record = {
            "machine_id": row["machine_id"],
            "Type": row["Type"],
            "Air temperature": float(
                row["Air temperature"]
            ),
            "Process temperature": float(
                row["Process temperature"]
            ),
            "Rotational speed": float(
                row["Rotational speed"]
            ),
            "Torque": float(
                row["Torque"]
            ),
            "Tool wear": float(
                row["Tool wear"]
            ),
        }

        result = predict_machine(
            record
        )

        results.append(result)

    # ---------------------------------------------------------
    # 3. Prepare report
    # ---------------------------------------------------------

    print(
        "\n[3/4] Creating prediction report..."
    )

    results_dataframe = pd.DataFrame(
        results
    )

    results_dataframe[
        "reason_codes"
    ] = results_dataframe[
        "reason_codes"
    ].apply(
        lambda reasons: ", ".join(reasons)
    )

    # Sort by overall risk first,
    # then failure probability.
    risk_order = {
        "HIGH": 0,
        "MEDIUM": 1,
        "LOW": 2,
    }

    results_dataframe[
        "risk_order"
    ] = results_dataframe[
        "overall_risk"
    ].map(
        risk_order
    )

    results_dataframe = (
        results_dataframe
        .sort_values(
            by=[
                "risk_order",
                "failure_probability",
            ],
            ascending=[
                True,
                False,
            ],
        )
        .drop(
            columns=["risk_order"]
        )
    )

    # ---------------------------------------------------------
    # 4. Save report
    # ---------------------------------------------------------

    print(
        "\n[4/4] Saving prediction report..."
    )

    results_dataframe.to_csv(
        OUTPUT_FILE,
        index=False,
    )

    print()
    print(
        f"Prediction report saved to:"
    )
    print(OUTPUT_FILE)

    # ---------------------------------------------------------
    # Display report
    # ---------------------------------------------------------

    print()
    print("=" * 100)
    print("MACHINE RISK REPORT")
    print("=" * 100)

    for _, row in results_dataframe.iterrows():

        print(
            f"{row['machine_id']:>5} | "
            f"ML: {row['failure_probability']:.2%} "
            f"({row['ml_risk']:<6}) | "
            f"Sensor: {row['sensor_risk']:<6} "
            f"({row['sensor_warning_count']} warnings) | "
            f"Overall: {row['overall_risk']:<6}"
        )

    print()
    print(
        "Batch prediction completed successfully."
    )


if __name__ == "__main__":
    main()