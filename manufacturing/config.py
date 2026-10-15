"""
Manufacturing configuration (environment driven) and logging.

Everything has a safe local default so the package runs with no Google Cloud
access. Set PM_STRICT_CONFIG=true in Cloud Run to fail fast at startup when a
required setting is missing, instead of silently degrading to local fallbacks.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent

DATA_DIR = ROOT / "data"
SAMPLE_DIR = DATA_DIR / "samples"
MODEL_DIR = ROOT / "models"
KNOWLEDGE_FILE = ROOT / "knowledge" / "maintenance_manual.txt"


def _env_bool(name: str, default: bool = False) -> bool:
    return os.environ.get(name, str(default)).strip().lower() in (
        "1",
        "true",
        "yes",
    )


# --- Google Cloud ---------------------------------------------------------
PROJECT_ID = os.environ.get("GOOGLE_CLOUD_PROJECT", "")
REGION = os.environ.get("GCP_REGION", "us-central1")
FIRESTORE_DATABASE = os.environ.get("FIRESTORE_DATABASE", "(default)")
BIGQUERY_DATASET = os.environ.get("BIGQUERY_DATASET", "pm_platform")
GCS_BUCKET = os.environ.get("GCS_BUCKET", "")

# --- Gemini ---------------------------------------------------------------
GEMINI_MODEL_NAME = os.environ.get("GEMINI_MODEL_NAME", "gemini-3.1-flash-lite")
GEMINI_API_KEY = os.environ.get("GOOGLE_API_KEY", "")
GEMINI_TIMEOUT_S = float(os.environ.get("GEMINI_TIMEOUT_S", "20"))
GEMINI_RETRIES = int(os.environ.get("GEMINI_RETRIES", "1"))
# Vertex AI (service-account auth, no API key) when explicitly requested, or
# when a project is configured and no API key is present.
USE_VERTEX = _env_bool(
    "GOOGLE_GENAI_USE_VERTEXAI",
    default=bool(PROJECT_ID) and not GEMINI_API_KEY,
)

STRICT = _env_bool("PM_STRICT_CONFIG", False)


class ConfigError(RuntimeError):
    """Raised at startup when strict configuration is violated."""


def gcp_available() -> bool:
    return bool(PROJECT_ID)


def validate() -> list[str]:
    """Return configuration problems; raise ConfigError if STRICT is set."""

    problems: list[str] = []

    if STRICT:
        if not PROJECT_ID:
            problems.append("GOOGLE_CLOUD_PROJECT is not set")
        if not (GEMINI_API_KEY or USE_VERTEX):
            problems.append(
                "No Gemini credentials: set GOOGLE_API_KEY or "
                "GOOGLE_GENAI_USE_VERTEXAI=true"
            )
        if not GEMINI_MODEL_NAME:
            problems.append("GEMINI_MODEL_NAME is empty")
        if not MODEL_DIR.exists() or not any(MODEL_DIR.glob("*_model.joblib")):
            problems.append(f"No trained models found in {MODEL_DIR}")

    if problems and STRICT:
        raise ConfigError("; ".join(problems))

    return problems


# --- Structured logging ---------------------------------------------------
class _JsonFormatter(logging.Formatter):
    """One JSON object per line; Cloud Run turns these into log entries."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "severity": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        extra = getattr(record, "fields", None)
        if extra:
            payload.update(extra)
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


_configured = False


def get_logger(name: str) -> logging.Logger:
    """Logger that writes JSON to stdout (configured once)."""

    global _configured

    if not _configured:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(_JsonFormatter())
        root = logging.getLogger("manufacturing")
        root.handlers = [handler]
        root.setLevel(os.environ.get("LOG_LEVEL", "INFO").upper())
        root.propagate = False
        _configured = True

    if not name.startswith("manufacturing"):
        name = f"manufacturing.{name}"

    return logging.getLogger(name)
