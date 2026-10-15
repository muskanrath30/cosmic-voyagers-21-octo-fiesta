"""
Reason codes and ML + sensor risk fusion.

Sensor rules are interpretable evidence, the ML model is the primary signal.

Fusion (replaces "take the more severe of the two", which let any noisy rule
raise a HIGH alert and caused alert fatigue):

    ML HIGH                       -> HIGH
    ML MEDIUM + sensor MEDIUM/HIGH -> HIGH
    ML LOW    + sensor HIGH        -> MEDIUM  (investigate, do not alarm)
    ML MEDIUM + sensor LOW         -> MEDIUM
    ML LOW    + sensor LOW/MEDIUM  -> LOW

For data-driven assets the "normal band" of every sensor comes from healthy
training rows (0.5th..99.5th percentile) saved by train.py in
models/<asset>_bands.json. Hand-set defaults are used only if that file is
missing.
"""

from __future__ import annotations

import json
import math

from manufacturing import config

NO_ANOMALY = "NO_MAJOR_SENSOR_ANOMALY"
INF = math.inf


def _num(record: dict, key: str, default: float = 0.0) -> float:
    try:
        value = float(record.get(key, default))
    except (TypeError, ValueError):
        return float(default)
    return value if math.isfinite(value) else float(default)


# --------------------------------------------------------------------------- #
# AI4I machine tool: validated thresholds from the original MVP
# --------------------------------------------------------------------------- #
def _machine_tool_codes(r: dict) -> list[str]:
    codes = []
    speed, torque = _num(r, "Rotational speed", 1500), _num(r, "Torque")

    if _num(r, "Tool wear") >= 120:
        codes.append("HIGH_TOOL_WEAR")
    if torque >= 50:
        codes.append("HIGH_TORQUE")
    if _num(r, "Process temperature") >= 315:
        codes.append("HIGH_PROCESS_TEMPERATURE")
    if _num(r, "Air temperature") >= 305:
        codes.append("HIGH_AIR_TEMPERATURE")
    if speed <= 1400:
        codes.append("LOW_ROTATIONAL_SPEED")
    if speed <= 1400 and torque >= 50:
        codes.append("HIGH_MECHANICAL_LOAD")

    return codes


# Low speed alone is common (~1 in 5 healthy rows) and HIGH_MECHANICAL_LOAD is
# derived from two other codes, so neither adds to the sensor-warning count.
_MACHINE_TOOL_UNCOUNTED = {"LOW_ROTATIONAL_SPEED", "HIGH_MECHANICAL_LOAD"}

# --------------------------------------------------------------------------- #
# Data-driven assets
# --------------------------------------------------------------------------- #
# feature -> (code when below band, code when above band); None = no code
_CODE_MAP = {
    "metro_compressor": {
        "TP2": ("LOW_SYSTEM_PRESSURE", None),
        "TP3": ("LOW_SYSTEM_PRESSURE", None),
        "Reservoirs": ("RESERVOIR_PRESSURE_MISMATCH", None),
        "Motor_current": (None, "HIGH_MOTOR_CURRENT"),
        "Oil_temperature": (None, "HIGH_OIL_TEMPERATURE"),
        "DV_pressure": (None, "DRYER_DISCHARGE_ANOMALY"),
        "LPS": (None, "LOW_PRESSURE_SWITCH_ACTIVE"),
    },
    "bearing": {
        "de_rms": (None, "HIGH_DRIVE_END_VIBRATION"),
        "fe_rms": (None, "HIGH_FAN_END_VIBRATION"),
        "de_kurtosis": (None, "IMPULSIVE_VIBRATION_KURTOSIS"),
        "fe_kurtosis": (None, "IMPULSIVE_VIBRATION_KURTOSIS"),
        "de_crest": (None, "HIGH_CREST_FACTOR"),
        "fe_crest": (None, "HIGH_CREST_FACTOR"),
    },
    "turbofan_engine": {},  # codes are generated as S<n>_HIGH / S<n>_LOW
}

# hand-set fallback bands (lo, hi), used only when no trained bands exist
DEFAULT_BANDS = {
    "metro_compressor": {
        "TP2": (8.8, INF), "TP3": (8.8, INF), "Reservoirs": (8.9, INF),
        "Motor_current": (-INF, 6.0), "Oil_temperature": (-INF, 68.0),
        "DV_pressure": (-INF, 0.5), "LPS": (-INF, 0.5),
    },
    "bearing": {
        "de_rms": (-INF, 0.25), "fe_rms": (-INF, 0.20),
        "de_kurtosis": (-INF, 5.0), "fe_kurtosis": (-INF, 5.0),
        "de_crest": (-INF, 4.0), "fe_crest": (-INF, 4.0),
    },
    "turbofan_engine": {
        "s2": (642.0, 644.5), "s3": (1585.0, 1592.0), "s4": (1400.0, 1420.0),
        "s7": (552.0, 556.0), "s8": (2387.0, 2390.5), "s9": (9040.0, 9070.0),
        "s11": (47.0, 48.5), "s12": (521.0, 524.0), "s13": (2388.0, 2391.0),
        "s14": (8120.0, 8150.0), "s15": (8.4, 8.6), "s17": (392.0, 394.0),
        "s20": (38.5, 39.3), "s21": (23.2, 23.5),
    },
}

# (codes for HIGH, codes for MEDIUM, codes that count as strong evidence)
_SENSOR_LEVELS = {
    "machine_tool": (3, 2, set()),
    "metro_compressor": (3, 2, {"LOW_SYSTEM_PRESSURE",
                                "RESERVOIR_PRESSURE_MISMATCH"}),
    "turbofan_engine": (4, 2, set()),
    "bearing": (3, 2, {"IMPULSIVE_VIBRATION_KURTOSIS", "HIGH_CREST_FACTOR"}),
}


def load_bands(asset: str) -> dict:
    """Trained bands {feature: {"lo","hi","median"}} or {} if not trained."""

    path = config.MODEL_DIR / f"{asset}_bands.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8")).get("features", {})
    except (OSError, ValueError):
        return {}


def _bands_for(asset: str, bands: dict | None) -> dict:
    if bands:
        return {f: (b["lo"], b["hi"]) for f, b in bands.items()}
    return DEFAULT_BANDS.get(asset, {})


def get_reason_codes(
    asset: str,
    record: dict,
    bands: dict | None = None,
) -> list[str]:
    """Interpretable sensor evidence for one record."""

    if asset == "machine_tool":
        codes = _machine_tool_codes(record)
        return codes or [NO_ANOMALY]

    codes: list[str] = []
    code_map = _CODE_MAP.get(asset, {})

    for feature, (lo, hi) in _bands_for(asset, bands).items():
        if feature not in record:
            continue
        value = _num(record, feature, default=float("nan"))
        if math.isnan(value):
            continue

        if asset == "turbofan_engine":
            low_code, high_code = f"{feature.upper()}_LOW", f"{feature.upper()}_HIGH"
        else:
            low_code, high_code = code_map.get(feature, (None, None))

        if value < lo and low_code and low_code not in codes:
            codes.append(low_code)
        elif value > hi and high_code and high_code not in codes:
            codes.append(high_code)

    return codes or [NO_ANOMALY]


def get_ml_risk(probability: float, threshold: float = 0.5) -> str:
    """HIGH at/above the validation-chosen operating threshold, MEDIUM from
    half of it."""

    if probability >= threshold:
        return "HIGH"
    if probability >= threshold / 2:
        return "MEDIUM"
    return "LOW"


def get_sensor_risk(asset: str, reason_codes: list[str]) -> str:
    if reason_codes == [NO_ANOMALY]:
        return "LOW"

    high_n, medium_n, strong = _SENSOR_LEVELS.get(asset, (3, 2, set()))

    counted = [
        c for c in reason_codes
        if not (asset == "machine_tool" and c in _MACHINE_TOOL_UNCOUNTED)
    ]
    n = len(counted)

    if n >= high_n:
        return "HIGH"
    if n >= medium_n or (n >= 1 and any(c in strong for c in counted)):
        return "MEDIUM"
    return "LOW"


_RANK = {"LOW": 0, "MEDIUM": 1, "HIGH": 2}
_LEVELS = ["LOW", "MEDIUM", "HIGH"]


def get_overall_risk(ml_risk: str, sensor_risk: str) -> str:
    ml, sensor = _RANK[ml_risk], _RANK[sensor_risk]

    if ml == 2:
        return "HIGH"
    if sensor == 2:
        return _LEVELS[min(ml + 1, 2)]
    if sensor == 1 and ml == 1:
        return "HIGH"
    return ml_risk


def get_recommendation(overall_risk: str) -> str:
    return {
        "HIGH": "Urgent maintenance inspection recommended",
        "MEDIUM": "Schedule maintenance inspection",
        "LOW": "Continue monitoring machine",
    }[overall_risk]
