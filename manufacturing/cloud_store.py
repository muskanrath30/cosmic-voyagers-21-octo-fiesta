"""
Google Cloud persistence for the Manufacturing track.

Everything is a no-op (returns False) when GOOGLE_CLOUD_PROJECT is not set, so
the package runs locally with no credentials. The shared pipeline keeps its own
Firestore decision save (stage 5); this module adds the manufacturing-specific
writes:

    Firestore  work_orders/<deterministic id>      (idempotent: retries
                                                    overwrite, never duplicate)
    BigQuery   predictions, decisions              (rows match
                                                    bigquery_schema.sql)
    BigQuery   raw_sensor_readings                 (see ingest_to_bigquery.py)
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone

from manufacturing import config

log = config.get_logger("cloud_store")

_firestore_client = None
_bq_client = None


def _firestore():
    global _firestore_client
    if _firestore_client is None and config.gcp_available():
        from google.cloud import firestore
        _firestore_client = firestore.Client(
            project=config.PROJECT_ID, database=config.FIRESTORE_DATABASE)
    return _firestore_client


def _bigquery():
    global _bq_client
    if _bq_client is None and config.gcp_available():
        from google.cloud import bigquery
        _bq_client = bigquery.Client(project=config.PROJECT_ID)
    return _bq_client


def work_order_id(asset: str, record_id: str, overall_risk: str) -> str:
    """Deterministic per asset + record + risk level + UTC day."""

    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    digest = hashlib.sha1(
        f"{asset}|{record_id}|{overall_risk}|{day}".encode()).hexdigest()
    return f"wo-{digest[:16]}"


def save_work_order(work_order: dict) -> bool:
    """Write the work order to Firestore. Returns True if persisted."""

    try:
        client = _firestore()
        if client is None:
            return False
        client.collection("work_orders").document(work_order["work_order_id"]).set(
            work_order)
        return True
    except Exception as exc:
        log.error(f"Firestore work-order write failed: {exc}")
        return False


def write_decision_rows(prediction: dict, work_order: dict | None) -> bool:
    """Append one row each to BigQuery predictions and decisions."""

    try:
        client = _bigquery()
        if client is None:
            return False

        prefix = f"{config.PROJECT_ID}.{config.BIGQUERY_DATASET}"
        prediction_id = uuid.uuid4().hex
        device_id = f"{prediction['asset']}:{prediction.get('id')}"

        errors = client.insert_rows_json(f"{prefix}.predictions", [{
            "prediction_id": prediction_id,
            "device_id": device_id,
            "model_name": prediction["model"],
            "model_version": prediction["model_version"],
            "prediction_type": "failure_probability",
            "predicted_value": prediction["score"],
            "features": json.dumps({
                "reason_codes": prediction["reason_codes"],
                "overall_risk": prediction["overall_risk"],
                "rul_cycles": prediction.get("rul_cycles"),
            }),
        }])

        if work_order is not None:
            errors += client.insert_rows_json(f"{prefix}.decisions", [{
                "decision_id": work_order["work_order_id"],
                "device_id": device_id,
                "prediction_id": prediction_id,
                "decision_type": work_order["action"],
                "severity": work_order["priority"].lower(),
                "rationale": work_order["summary"],
                "actor": "system",
                "status": "open",
            }])

        if errors:
            log.error(f"BigQuery insert errors: {errors[:2]}")
            return False
        return True
    except Exception as exc:
        log.error(f"BigQuery write failed: {exc}")
        return False
