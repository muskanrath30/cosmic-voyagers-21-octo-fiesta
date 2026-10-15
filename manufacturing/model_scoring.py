"""
Manufacturing Stage 2: Model Scoring

Team pipeline contract (unchanged):

    score(domain, record) -> {
        "score": float,          # failure probability
        "reason_code": str,
        "factors": list[str],
        "model": str,
        ...extra manufacturing fields...
    }

The shared pipeline calls score("manufacturing", record).

The record may carry an "asset" key (machine_tool, metro_compressor,
turbofan_engine, bearing). Without it the asset is inferred from the field
names, and records using the original AI4I fields keep working as machine_tool.

What this stage does:
    1. validates the record (numeric, finite, enough fields)
    2. runs the asset's trained model (falls back to a heuristic, flagged
       "degraded": true, if no trained model is available)
    3. derives reason codes from healthy-data sensor bands
    4. fuses ML risk and sensor risk (see risk_rules.py)
    5. retrieves the matching maintenance-manual sections (RAG)
"""

from __future__ import annotations

import sys
from pathlib import Path

if __package__ in (None, ""):  # allow running this file directly
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import json
import threading

import joblib
import pandas as pd

from manufacturing import config, datasets, risk_rules
from manufacturing.preprocessing import InvalidRecordError, build_feature_row
from manufacturing.rag_retriever import retrieve_sections
from manufacturing.train import metrics_path, model_path, rul_path

log = config.get_logger("scoring")

_LEGACY_THRESHOLD = 0.30   # original validated AI4I operating point
_DEFAULT_THRESHOLD = 0.50

_LOCK = threading.Lock()
_CACHE: dict[str, dict] = {}
_WARNED: set[str] = set()  # log "no trained model" once per asset, not per call


# --------------------------------------------------------------------------- #
# Artifact loading (cached, thread-safe)
# --------------------------------------------------------------------------- #
def _load_bundle(asset: str) -> dict:
    """Model, RUL model, metrics, bands for one asset (cached)."""

    with _LOCK:
        if asset in _CACHE:
            return _CACHE[asset]

        bundle = {"model": None, "rul": None, "metrics": {}, "bands": {}}

        mp = model_path(asset)
        if mp.exists():
            try:
                bundle["model"] = joblib.load(mp)
            except Exception as exc:  # e.g. built with another sklearn version
                log.error(f"could not load {asset} model: {exc}")

        rp = rul_path(asset)
        if rp.exists():
            try:
                bundle["rul"] = joblib.load(rp)
            except Exception as exc:
                log.error(f"could not load {asset} RUL model: {exc}")

        if metrics_path(asset).exists():
            bundle["metrics"] = json.loads(
                metrics_path(asset).read_text(encoding="utf-8"))

        bundle["bands"] = risk_rules.load_bands(asset)

        _CACHE[asset] = bundle
        return bundle


def reload_models() -> None:
    """Drop cached artifacts (call after retraining)."""
    with _LOCK:
        _CACHE.clear()


def model_status() -> dict:
    """Per-asset readiness for health checks."""

    out = {}
    for asset in datasets.ASSETS:
        b = _load_bundle(asset)
        out[asset] = {
            "model_loaded": b["model"] is not None,
            "data_source": b["metrics"].get("data_source"),
            "trained_at": b["metrics"].get("trained_at"),
        }
    return out


# --------------------------------------------------------------------------- #
# Fallback
# --------------------------------------------------------------------------- #
def _fallback_probability(asset: str, reason_codes: list[str]) -> float:
    """Heuristic used only when no trained model is available."""

    n = len([c for c in reason_codes if c != risk_rules.NO_ANOMALY])

    if asset == "machine_tool":
        weights = {
            "HIGH_TOOL_WEAR": 0.20, "HIGH_TORQUE": 0.20,
            "HIGH_PROCESS_TEMPERATURE": 0.15, "HIGH_AIR_TEMPERATURE": 0.10,
            "LOW_ROTATIONAL_SPEED": 0.15, "HIGH_MECHANICAL_LOAD": 0.15,
        }
        return min(round(sum(weights.get(c, 0) for c in reason_codes), 4), 0.99)

    return float(min(0.9, 0.15 + 0.25 * n))


# --------------------------------------------------------------------------- #
# Public entrypoint
# --------------------------------------------------------------------------- #
def score(domain: str, record: dict) -> dict:
    """Score one record. See module docstring for the contract."""

    if domain not in ("manufacturing", "sensor"):
        raise ValueError(f"Unsupported Manufacturing domain: {domain}")

    if not isinstance(record, dict):
        raise InvalidRecordError("record must be an object")

    asset = datasets.infer_asset(record)
    spec = datasets.get_spec(asset)
    bundle = _load_bundle(asset)
    bands = bundle["bands"]

    defaults = {f: b["median"] for f, b in bands.items() if "median" in b}
    defaults.update({f: b["mode"] for f, b in bands.items() if "mode" in b})

    allowed = {"Type": {"L", "M", "H"}} if asset == "machine_tool" else {}
    row = build_feature_row(
        spec["features"], spec["categorical"], record,
        defaults=defaults, allowed_categories=allowed,
    )

    reason_codes = risk_rules.get_reason_codes(
        asset, {**record, **row}, bands=_numeric_bands(bands))

    degraded = bundle["model"] is None
    if not degraded:
        frame = pd.DataFrame([row], columns=spec["features"])
        probability = float(bundle["model"].predict_proba(frame)[0][1])
        model_name = "random_forest"
    else:
        if asset not in _WARNED:
            _WARNED.add(asset)
            log.warning(f"no trained model for {asset}; using heuristic fallback",
                        extra={"fields": {"asset": asset, "degraded": True}})
        probability = _fallback_probability(asset, reason_codes)
        model_name = "heuristic_fallback"

    probability = round(probability, 4)

    threshold = bundle["metrics"].get(
        "operating_threshold",
        _LEGACY_THRESHOLD if asset == "machine_tool" else _DEFAULT_THRESHOLD,
    )

    ml_risk = risk_rules.get_ml_risk(probability, threshold)
    sensor_risk = risk_rules.get_sensor_risk(asset, reason_codes)
    overall_risk = risk_rules.get_overall_risk(ml_risk, sensor_risk)

    factors = [c for c in reason_codes if c != risk_rules.NO_ANOMALY] or [
        "no major sensor anomaly identified"
    ]

    try:
        sections = retrieve_sections(reason_codes)
    except Exception as exc:  # retrieval must never break scoring
        log.error(f"RAG retrieval failed: {exc}")
        sections = []

    result = {
        "score": probability,
        "reason_code": reason_codes[0],
        "factors": factors[:6],
        "model": model_name,
        # manufacturing extras
        "asset": asset,
        "asset_name": spec["name"],
        "id": record.get("id") or record.get("machine_id"),
        "ml_risk": ml_risk,
        "sensor_risk": sensor_risk,
        "overall_risk": overall_risk,
        "operating_threshold": threshold,
        "reason_codes": reason_codes,
        "recommendation": risk_rules.get_recommendation(overall_risk),
        "model_version": _model_version(asset, bundle),
        "data_source": bundle["metrics"].get("data_source", "unknown"),
        "degraded": degraded,
        "knowledge_context": "\n\n".join(s["text"] for s in sections),
        "knowledge_sources": [s["title"] for s in sections],
    }

    if bundle["rul"] is not None:
        frame = pd.DataFrame([row], columns=spec["features"])
        result["rul_cycles"] = round(float(bundle["rul"].predict(frame)[0]), 1)

    return result


def _numeric_bands(bands: dict) -> dict:
    return {f: b for f, b in bands.items() if "lo" in b}


def _model_version(asset: str, bundle: dict) -> str:
    stamp = bundle["metrics"].get("trained_at", "untrained")[:10]
    return f"{asset}-{stamp}"


# --------------------------------------------------------------------------- #
# Local test
# --------------------------------------------------------------------------- #
if __name__ == "__main__":

    test_machine = {
        "id": "M004",
        "machine_id": "M004",
        "Type": "L",
        "Air temperature": 310.0,
        "Process temperature": 320.0,
        "Rotational speed": 1350.0,
        "Torque": 60.0,
        "Tool wear": 180.0,
    }

    result = score("manufacturing", test_machine)

    print()
    print("=" * 80)
    print("MANUFACTURING MODEL SCORING TEST")
    print("=" * 80)

    for key, value in result.items():
        if key != "knowledge_context":
            print(f"{key}: {value}")
