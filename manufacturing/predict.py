from pathlib import Path

import joblib
import pandas as pd

from gemini_reasoning import generate_explanation


ROOT = Path(__file__).resolve().parent

MODEL_FILE = (
    ROOT
    / "model"
    / "manufacturing_ai4i_model.joblib"
)


def get_reason_codes(
    record: dict,
) -> list[str]:
    """
    Identify sensor conditions that may indicate
    increased maintenance risk.
    """

    reasons = []

    if record["Tool wear"] >= 120:
        reasons.append(
            "HIGH_TOOL_WEAR"
        )

    if record["Torque"] >= 50:
        reasons.append(
            "HIGH_TORQUE"
        )

    if record["Process temperature"] >= 315:
        reasons.append(
            "HIGH_PROCESS_TEMPERATURE"
        )

    if record["Air temperature"] >= 305:
        reasons.append(
            "HIGH_AIR_TEMPERATURE"
        )

    if record["Rotational speed"] <= 1400:
        reasons.append(
            "LOW_ROTATIONAL_SPEED"
        )

    if (
        record["Rotational speed"] <= 1400
        and record["Torque"] >= 50
    ):
        reasons.append(
            "HIGH_MECHANICAL_LOAD"
        )

    if not reasons:
        reasons.append(
            "NO_MAJOR_SENSOR_ANOMALY"
        )

    return reasons


def get_ml_risk(
    probability: float,
) -> str:
    """
    Convert ML failure probability into
    an ML-only risk level.
    """

    if probability >= 0.30:
        return "HIGH"

    if probability >= 0.15:
        return "MEDIUM"

    return "LOW"


def get_sensor_risk(
    reason_codes: list[str],
) -> str:
    """
    Determine sensor-condition risk independently
    from the ML model.
    """

    if (
        "NO_MAJOR_SENSOR_ANOMALY"
        in reason_codes
    ):
        return "LOW"

    warning_count = len(
        reason_codes
    )

    if warning_count >= 4:
        return "HIGH"

    if warning_count >= 2:
        return "MEDIUM"

    return "LOW"


def get_overall_risk(
    ml_risk: str,
    sensor_risk: str,
) -> str:
    """
    Combine ML risk and sensor risk.

    The more severe signal determines
    the overall risk.
    """

    risk_priority = {
        "LOW": 0,
        "MEDIUM": 1,
        "HIGH": 2,
    }

    if (
        risk_priority[sensor_risk]
        > risk_priority[ml_risk]
    ):
        return sensor_risk

    return ml_risk


def get_recommendation(
    overall_risk: str,
) -> str:
    """
    Generate a maintenance recommendation.

    The system does not automatically stop
    physical equipment.
    """

    if overall_risk == "HIGH":
        return (
            "Urgent maintenance inspection recommended"
        )

    if overall_risk == "MEDIUM":
        return (
            "Schedule maintenance inspection"
        )

    return (
        "Continue monitoring machine"
    )


def predict_machine(
    record: dict,
) -> dict:
    """
    Run predictive-maintenance inference
    for one machine.
    """

    model = joblib.load(
        MODEL_FILE
    )

    dataframe = pd.DataFrame(
        [
            {
                "Air temperature":
                    record["Air temperature"],

                "Process temperature":
                    record["Process temperature"],

                "Rotational speed":
                    record["Rotational speed"],

                "Torque":
                    record["Torque"],

                "Tool wear":
                    record["Tool wear"],

                "Type":
                    record["Type"],
            }
        ]
    )

    probability = model.predict_proba(
        dataframe
    )[0][1]

    probability = float(
        probability
    )

    reason_codes = get_reason_codes(
        record
    )

    ml_risk = get_ml_risk(
        probability
    )

    sensor_risk = get_sensor_risk(
        reason_codes
    )

    overall_risk = get_overall_risk(
        ml_risk,
        sensor_risk,
    )

    recommendation = get_recommendation(
        overall_risk
    )

    prediction = {
        "machine_id":
            record["machine_id"],

        "failure_probability":
            round(
                probability,
                4,
            ),

        "ml_risk":
            ml_risk,

        "sensor_warning_count":
            (
                0
                if "NO_MAJOR_SENSOR_ANOMALY"
                in reason_codes
                else len(reason_codes)
            ),

        "sensor_risk":
            sensor_risk,

        "overall_risk":
            overall_risk,

        "reason_codes":
            reason_codes,

        "recommendation":
            recommendation,

        "model_version":
            "manufacturing-ai4i-v1",
    }

    explanation, reasoning_source = (
        generate_explanation(
            prediction
        )
    )

    prediction["explanation"] = (
        explanation
    )

    prediction["reasoning_source"] = (
        reasoning_source
    )

    return prediction


if __name__ == "__main__":

    test_machine = {
        "machine_id": "M004",
        "Type": "L",
        "Air temperature": 310.0,
        "Process temperature": 320.0,
        "Rotational speed": 1350,
        "Torque": 60.0,
        "Tool wear": 180,
    }

    result = predict_machine(
        test_machine
    )

    print()
    print("=" * 80)
    print("MANUFACTURING PREDICTION")
    print("=" * 80)

    print()

    for key, value in result.items():

        print(
            f"{key}: {value}"
        )