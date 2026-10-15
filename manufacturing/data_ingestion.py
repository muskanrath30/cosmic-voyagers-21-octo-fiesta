"""
Manufacturing Stage 1: Data Ingestion

The shared pipeline expects:
    get_record(domain, record_id)
    get_sample_records(domain)

Records come from two places:
    * data/machine_data.csv        10 hand-made CNC machines (M001..M010)
    * the asset training frames    deterministic, balanced demo samples for the
                                   metro compressor (MC-###), turbofan engine
                                   (TF-###) and bearing (BR-###)

Every record carries its "asset" so the scoring stage knows which model to use.
Samples are deterministic (fixed seed) so the same ID always returns the same
record between restarts.

replay_stream(asset) returns an ordered sequence of readings for the
Sensor Monitor agent / dashboard replay (for the turbofan: one engine's
trajectory from healthy to failure).
"""

from __future__ import annotations

import csv
import functools
import sys
from pathlib import Path

if __package__ in (None, ""):  # allow `python data_ingestion.py`
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd

from manufacturing import config, datasets

_MACHINE_DATA_PATH = config.DATA_DIR / "machine_data.csv"
_PREFIX = {"metro_compressor": "MC", "turbofan_engine": "TF", "bearing": "BR"}
_SAMPLES_PER_ASSET = 6
_SEED = 7


def _is_manufacturing(domain: str) -> bool:
    return domain in ("manufacturing", "sensor")


@functools.lru_cache(maxsize=1)
def _machine_records() -> tuple[dict, ...]:
    """The 10 hand-made CNC machines."""

    if not _MACHINE_DATA_PATH.exists():
        return ()

    records = []
    with open(_MACHINE_DATA_PATH, newline="", encoding="utf-8") as file:
        for row in csv.DictReader(file):
            records.append({
                "asset": "machine_tool",
                "id": row["machine_id"],
                "machine_id": row["machine_id"],
                "Type": row["Type"],
                "Air temperature": float(row["Air temperature"]),
                "Process temperature": float(row["Process temperature"]),
                "Rotational speed": float(row["Rotational speed"]),
                "Torque": float(row["Torque"]),
                "Tool wear": float(row["Tool wear"]),
            })
    return tuple(records)


@functools.lru_cache(maxsize=None)
def _asset_samples(asset: str) -> tuple[dict, ...]:
    """Balanced deterministic sample: about a third failing, the rest healthy."""

    if not datasets.has_data(asset):
        return ()

    spec = datasets.get_spec(asset)
    df = datasets.load_training_frame(asset)
    target = spec["target"]

    n_pos = max(1, _SAMPLES_PER_ASSET // 3)
    pos = df[df[target] == 1]
    neg = df[df[target] == 0]
    sample = pd.concat([
        pos.sample(min(n_pos, len(pos)), random_state=_SEED),
        neg.sample(min(_SAMPLES_PER_ASSET - n_pos, len(neg)), random_state=_SEED),
    ])

    extras = [c for c in ("unit", "cycle") if c in df.columns]
    records = []
    for i, (_, row) in enumerate(sample.iterrows(), start=1):
        rec = {"asset": asset, "id": f"{_PREFIX[asset]}-{i:03d}"}
        rec.update({c: float(row[c]) for c in spec["features"]})
        rec.update({c: (str(row[c]) if c == "unit" else float(row[c])) for c in extras})
        records.append(rec)
    return tuple(records)


def get_sample_records(domain: str, asset: str | None = None) -> list[dict]:
    """Manufacturing demo records (optionally for one asset)."""

    if not _is_manufacturing(domain):
        return []

    out: list[dict] = []
    if asset in (None, "machine_tool"):
        out.extend(dict(r) for r in _machine_records())
    for aid in datasets.ASSETS:
        if aid != "machine_tool" and asset in (None, aid):
            out.extend(dict(r) for r in _asset_samples(aid))
    return out


def get_record(domain: str, record_id: str) -> dict | None:
    """Look up one record by ID, e.g. get_record("manufacturing", "M004")."""

    if not _is_manufacturing(domain):
        return None

    for record in get_sample_records(domain):
        if record["id"] == record_id:
            return record.copy()
    return None


def list_all_records() -> list[dict]:
    return get_sample_records("manufacturing")


def replay_stream(asset: str, steps: int = 20) -> list[dict]:
    """
    Ordered readings for a live-monitoring replay.

    Turbofan: one engine (the median-length one) sampled evenly from its first
    cycle to its last. Other assets: the first `steps` rows in file order.
    """

    if not datasets.has_data(asset):
        return []

    spec = datasets.get_spec(asset)
    df = datasets.load_training_frame(asset)

    if asset == "turbofan_engine":
        lengths = df.groupby("unit")["cycle"].max().sort_values()
        unit = lengths.index[len(lengths) // 2]
        engine = df[df["unit"] == unit].sort_values("cycle")
        picks = engine.iloc[
            [int(i) for i in pd.Series(range(steps)).mul(len(engine) - 1).div(max(steps - 1, 1))]
        ]
    else:
        picks = df.head(steps)

    records = []
    for i, (_, row) in enumerate(picks.iterrows(), start=1):
        rec = {"asset": asset, "id": f"{_PREFIX.get(asset, asset)}-STREAM-{i:03d}", "step": i}
        rec.update({c: float(row[c]) for c in spec["features"]})
        if asset == "turbofan_engine":
            rec["cycle"] = float(row["cycle"])
        records.append(rec)
    return records


if __name__ == "__main__":

    print("=" * 80)
    print("MANUFACTURING DATA INGESTION TEST")
    print("=" * 80)

    records = get_sample_records("manufacturing")
    print(f"Loaded records: {len(records)}")

    for record in records:
        print(f"{record['id']:<8} asset={record['asset']}")
