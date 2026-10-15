"""
Asset registry and dataset loaders for the Manufacturing track.

Four assets share one pipeline:

    machine_tool      AI4I 2020 (original MVP, synthetic, 10k rows)
    metro_compressor  MetroPT-3 (real metro air compressor, UCI 791)
    turbofan_engine   NASA C-MAPSS (run-to-failure simulation, FD001-FD004)
    bearing           CWRU bearing (real lab rig, seeded faults)

Each loader returns (dataframe, source) where source is "real" or
"synthetic_standin". The source is written into metrics.json so the team can
state plainly which results come from real data.
"""

from __future__ import annotations

import functools

import numpy as np
import pandas as pd

from manufacturing import config
from manufacturing.preprocessing import (
    CATEGORICAL_FEATURES as AI4I_CATEGORICAL,
    NUMERIC_FEATURES as AI4I_NUMERIC,
    TARGET as AI4I_TARGET,
    prepare_dataframe,
)

# --------------------------------------------------------------------------- #
# AI4I 2020 (machine_tool)
# --------------------------------------------------------------------------- #
AI4I_FILE = config.DATA_DIR / "ai4i2020.csv"


def load_ai4i() -> tuple[pd.DataFrame, str]:
    if not AI4I_FILE.exists():
        raise FileNotFoundError(
            f"{AI4I_FILE} not found. Run: python download_dataset.py"
        )
    df = prepare_dataframe(pd.read_csv(AI4I_FILE))
    return df, "synthetic_published"  # AI4I is a published synthetic dataset


# --------------------------------------------------------------------------- #
# NASA C-MAPSS (turbofan_engine)
# --------------------------------------------------------------------------- #
CMAPSS_COLUMNS = (
    ["unit", "cycle", "op1", "op2", "op3"] + [f"s{i}" for i in range(1, 22)]
)
# sensors that are ~constant in FD001 are dropped
CMAPSS_FEATURES = [
    f"s{i}" for i in [2, 3, 4, 7, 8, 9, 11, 12, 13, 14, 15, 17, 20, 21]
]
CMAPSS_RUL_CAP = 125
CMAPSS_FAILURE_WINDOW = 30


def load_cmapss() -> tuple[pd.DataFrame, str]:
    """Load every train_FD00x.txt present (FD001 is bundled)."""

    frames = []
    for path in sorted(config.SAMPLE_DIR.glob("train_FD00*.txt")):
        fd = path.stem.split("_")[-1]
        df = pd.read_csv(path, sep=r"\s+", header=None, names=CMAPSS_COLUMNS)
        df["unit"] = fd + "-" + df["unit"].astype(str)  # unique across subsets
        frames.append(df)

    if not frames:
        raise FileNotFoundError(
            f"No train_FD00x.txt in {config.SAMPLE_DIR}"
        )

    df = pd.concat(frames, ignore_index=True)
    last = df.groupby("unit")["cycle"].transform("max")
    df["rul"] = (last - df["cycle"]).clip(upper=CMAPSS_RUL_CAP)
    df["failure_soon"] = (df["rul"] <= CMAPSS_FAILURE_WINDOW).astype(int)
    return df, "real_simulation"  # NASA simulation, not field data


# --------------------------------------------------------------------------- #
# MetroPT-3 (metro_compressor)
# --------------------------------------------------------------------------- #
METROPT_FEATURES = [
    "TP2", "TP3", "H1", "DV_pressure", "Reservoirs", "Oil_temperature",
    "Motor_current", "COMP", "DV_electric", "Towers", "MPG", "LPS",
    "Pressure_switch", "Oil_level", "Caudal_impulses",
]
_METROPT_MEANS = {
    "TP2": 9.3, "TP3": 9.3, "H1": 9.3, "DV_pressure": 0.0, "Reservoirs": 9.3,
    "Oil_temperature": 60.0, "Motor_current": 4.0, "COMP": 0.9,
    "DV_electric": 0.1, "Towers": 0.5, "MPG": 0.9, "LPS": 0.05,
    "Pressure_switch": 0.2, "Oil_level": 0.05, "Caudal_impulses": 0.9,
}


def _metropt_synthetic(n: int, seed: int = 7) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rows = []
    for _ in range(n):
        anomalous = rng.random() < 0.30
        r = {
            k: v + rng.normal(0, abs(v) * 0.06 + 0.02)
            for k, v in _METROPT_MEANS.items()
        }
        if anomalous and rng.random() < 0.7:
            r["TP2"] -= rng.uniform(0.1, 0.6)
            r["TP3"] -= rng.uniform(0.1, 0.6)
            r["Reservoirs"] -= rng.uniform(0.1, 0.5)
            r["Motor_current"] += rng.uniform(0.5, 2.0)
            r["Oil_temperature"] += rng.uniform(1, 4)
        r["anomaly"] = int(anomalous)
        rows.append(r)
    return pd.DataFrame(rows)


def load_metropt() -> tuple[pd.DataFrame, str]:
    path = config.SAMPLE_DIR / "metropt_sample.csv"
    if path.exists():
        df = pd.read_csv(path)
        df = df.rename(columns={"DV_eletric": "DV_electric"})  # UCI typo
        missing = [c for c in METROPT_FEATURES if c not in df.columns]
        if missing:
            raise ValueError(f"{path.name} is missing columns: {missing}")
        if "timestamp" in df.columns:
            df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
            df["hour_block"] = df["timestamp"].dt.floor("h").astype(str)
        return df, "real"
    return _metropt_synthetic(2000), "synthetic_standin"


# --------------------------------------------------------------------------- #
# CWRU bearing (bearing)
# --------------------------------------------------------------------------- #
CWRU_FEATURES = [
    "de_rms", "de_kurtosis", "de_skew", "de_peak", "de_crest",
    "fe_rms", "fe_kurtosis", "fe_skew", "fe_peak", "fe_crest",
]


def _cwru_synthetic(n: int, seed: int = 11) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rows = []
    for _ in range(n):
        faulty = rng.random() < 0.5
        base = 0.05 if not faulty else 0.11
        rows.append({
            "de_rms": base + rng.normal(0, 0.04),
            "de_kurtosis": 3.0 + (1.0 if faulty else 0.0) + rng.normal(0, 1.3),
            "de_skew": rng.normal(0, 0.4),
            "de_peak": base * 3 + rng.normal(0, 0.09),
            "de_crest": 3.0 + (0.4 if faulty else 0.0) + rng.normal(0, 0.8),
            "fe_rms": base * 0.8 + rng.normal(0, 0.04),
            "fe_kurtosis": 3.0 + (0.8 if faulty else 0.0) + rng.normal(0, 1.3),
            "fe_skew": rng.normal(0, 0.4),
            "fe_peak": base * 2.5 + rng.normal(0, 0.09),
            "fe_crest": 3.0 + (0.35 if faulty else 0.0) + rng.normal(0, 0.8),
            "fault": int(faulty),
        })
    return pd.DataFrame(rows)


def load_cwru() -> tuple[pd.DataFrame, str]:
    path = config.SAMPLE_DIR / "cwru_sample.npz"
    if path.exists():
        data = np.load(path, allow_pickle=False)
        df = pd.DataFrame(data["X"], columns=CWRU_FEATURES)
        df["fault"] = data["y"]
        if "src" in data.files:  # source file id: used to group windows
            df["source_file"] = data["src"]
        return df, "real"
    return _cwru_synthetic(1500), "synthetic_standin"


# --------------------------------------------------------------------------- #
# Registry
# --------------------------------------------------------------------------- #
LEGACY_ASSET = "machine_tool"

ASSETS: dict[str, dict] = {
    "machine_tool": {
        "name": "CNC Machine Tool",
        "description": "Milling machine records (AI4I 2020): tool wear, torque, "
                       "temperatures and rotational speed.",
        "dataset": "AI4I 2020 Predictive Maintenance",
        "features": AI4I_NUMERIC + AI4I_CATEGORICAL,
        "categorical": AI4I_CATEGORICAL,
        "target": AI4I_TARGET,
        "group": None,
        "loader": load_ai4i,
        "id_field": "machine_id",
        "signature": "Tool wear",
    },
    "metro_compressor": {
        "name": "Metro Air Compressor (APU)",
        "description": "Air-production-unit compressor on a Porto metro train; "
                       "pressures, motor current and oil temperature.",
        "dataset": "MetroPT-3 (UCI 791)",
        "features": METROPT_FEATURES,
        "categorical": [],
        "target": "anomaly",
        "group": "hour_block",
        "loader": load_metropt,
        "signature": "TP2",
    },
    "turbofan_engine": {
        "name": "Turbofan Engine",
        "description": "NASA C-MAPSS turbofan fleet; predicts failure within "
                       f"the next {CMAPSS_FAILURE_WINDOW} operating cycles.",
        "dataset": "NASA C-MAPSS",
        "features": CMAPSS_FEATURES,
        "categorical": [],
        "target": "failure_soon",
        "group": "unit",  # grouped split: no engine in both train and test
        "loader": load_cmapss,
        "signature": "s2",
    },
    "bearing": {
        "name": "Rolling-Element Bearing",
        "description": "CWRU drive-end/fan-end vibration statistics; normal vs "
                       "faulty bearing.",
        "dataset": "CWRU Bearing",
        "features": CWRU_FEATURES,
        "categorical": [],
        "target": "fault",
        "group": "source_file",
        "loader": load_cwru,
        "signature": "de_rms",
    },
}


class UnknownAssetError(ValueError):
    """Raised for an asset id that is not registered."""


def get_spec(asset: str) -> dict:
    if asset not in ASSETS:
        raise UnknownAssetError(
            f"Unknown asset '{asset}'. Valid: {sorted(ASSETS)}"
        )
    return ASSETS[asset]


def list_assets() -> list[dict]:
    return [
        {
            "id": aid,
            "name": s["name"],
            "description": s["description"],
            "dataset": s["dataset"],
        }
        for aid, s in ASSETS.items()
    ]


def feature_columns(asset: str) -> list[str]:
    return get_spec(asset)["features"]


def infer_asset(record: dict) -> str:
    """Pick the asset for a record: explicit 'asset' key, else by signature."""

    explicit = record.get("asset")
    if explicit:
        get_spec(str(explicit))  # raises UnknownAssetError if invalid
        return str(explicit)

    for aid, spec in ASSETS.items():
        if spec["signature"] in record:
            return aid

    return LEGACY_ASSET


@functools.lru_cache(maxsize=None)
def _load(asset: str) -> tuple[pd.DataFrame, str]:
    return get_spec(asset)["loader"]()


def load_training_frame(asset: str) -> pd.DataFrame:
    return _load(asset)[0]


def data_source(asset: str) -> str:
    return _load(asset)[1]


def has_data(asset: str) -> bool:
    try:
        _load(asset)
        return True
    except FileNotFoundError:
        return False
