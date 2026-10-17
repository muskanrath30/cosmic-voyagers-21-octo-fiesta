"""
Entrypoint for Cloud Run deployment.
Exposes the shared pipeline as HTTP endpoints:

    GET  /                          dashboard
    GET  /health                    liveness + manufacturing model status
    GET  /api/records               BFSI samples (unchanged) or ?domain=manufacturing
    POST /api/score                 shared five-stage pipeline (any domain)
    GET  /api/decisions             decision history
    GET  /api/manufacturing/stream  sensor replay for the live-monitoring demo
    POST /api/agents/run            Sensor Monitor -> Prediction -> Diagnosis -> Work Order

Local test:  python main.py        (then open http://localhost:8080)
Cloud Run:   this same file is what the Dockerfile runs.

BFSI data is optional: if the PaySim / loan CSVs are not in the image, only the
BFSI routes return 503; manufacturing keeps working.
"""
import asyncio
import os
import threading
import time
from collections import defaultdict, deque
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from dotenv import load_dotenv
load_dotenv()

from shared.pipeline import run_pipeline
from shared.state_store import list_decisions

BASE_DIR = Path(__file__).resolve().parent
PUBLIC_DIR = BASE_DIR / "public"

MANUFACTURING_DOMAINS = ("manufacturing", "sensor")

app = FastAPI()


# ---------------------------------------------------------------------------
# Public-endpoint protection: small per-IP rate limit on the routes that call
# Gemini and write to Firestore. Cloud Run --max-instances caps total cost;
# this stops one client from using the whole budget.
# ---------------------------------------------------------------------------
_RATE_LIMIT_PER_MIN = int(os.environ.get("RATE_LIMIT_PER_MIN", "30"))
_LIMITED_PATHS = ("/api/score", "/api/agents/run")
_hits: dict = defaultdict(deque)
_hits_lock = threading.Lock()


@app.middleware("http")
async def rate_limit(request: Request, call_next):
    if request.url.path in _LIMITED_PATHS and _RATE_LIMIT_PER_MIN > 0:
        forwarded = request.headers.get("x-forwarded-for", "")
        client = (forwarded.split(",")[0].strip() if forwarded
                  else (request.client.host if request.client else "unknown"))
        now = time.monotonic()
        with _hits_lock:
            window = _hits[client]
            while window and now - window[0] > 60:
                window.popleft()
            if len(window) >= _RATE_LIMIT_PER_MIN:
                return JSONResponse(
                    {"detail": "Too many requests. Please wait a minute."},
                    status_code=429,
                )
            window.append(now)
    return await call_next(request)


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------
class ScoreRequest(BaseModel):
    domain: Optional[str] = "transaction"  # transaction | loan | manufacturing
    record: Dict[str, Any] = Field(default_factory=dict)


class AgentRunRequest(BaseModel):
    record: Dict[str, Any] = Field(default_factory=dict)
    mode: Optional[str] = "plain"  # plain | adk


def _bfsi_list_all_records():
    """Import BFSI lazily: its module loads large CSVs at import time."""
    try:
        from bfsi.data_ingestion import list_all_records
    except Exception as e:
        raise HTTPException(
            status_code=503,
            detail="BFSI datasets are not available in this deployment.",
        ) from e
    return list_all_records()


def _resolve_manufacturing_record(record: Dict[str, Any]) -> Dict[str, Any]:
    """Accept either a full record or {"id": "TF-001"}."""
    from manufacturing import data_ingestion

    if record.get("id") and len(record) == 1:
        found = data_ingestion.get_record("manufacturing", record["id"])
        if not found:
            raise HTTPException(status_code=404, detail="Unknown record id.")
        return found
    if not record.get("id"):
        raise HTTPException(status_code=400, detail="A record id is required.")
    return record


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@app.get("/")
def index():
    return FileResponse(PUBLIC_DIR / "index.html")


@app.get("/health")
def health():
    # Cap the read: counting every decision in Firestore on each probe is slow
    # and costs a read per document.
    try:
        persisted = len(list_decisions(limit=100))
    except Exception:
        persisted = -1

    body = {
        "status": "ok",
        "service": "predictive-maintenance-copilot",
        "persisted_decisions": persisted,
    }
    try:
        from manufacturing import gemini_reasoning, model_scoring

        body["manufacturing"] = {
            "models": model_scoring.model_status(),
            "gemini": gemini_reasoning.get_stats(),
        }
    except Exception as e:
        body["manufacturing"] = {"error": str(e)}
    return body


@app.get("/api/records")
def records(domain: str = "bfsi"):
    if domain in MANUFACTURING_DOMAINS:
        from manufacturing import data_ingestion

        return {"records": data_ingestion.list_all_records()}
    return _bfsi_list_all_records()


@app.get("/api/decisions")
def decisions():
    return {"decisions": list_decisions(limit=100)}


@app.post("/api/score")
def score_record(body: ScoreRequest):
    domain = body.domain if body.domain in ("loan", "manufacturing", "sensor") else "transaction"
    record = body.record
    if not record.get("id"):
        raise HTTPException(status_code=400, detail="A record id is required.")

    try:
        return run_pipeline(domain, record)
    except ValueError as e:
        # Manufacturing validation errors (bad/missing sensor values, unknown
        # asset) are the caller's mistake, not a server fault.
        if domain in MANUFACTURING_DOMAINS:
            raise HTTPException(status_code=422, detail=str(e)) from e
        raise HTTPException(status_code=500, detail="Unable to score the record.") from e
    except Exception as e:
        raise HTTPException(status_code=500, detail="Unable to score the record.") from e


@app.get("/api/manufacturing/stream")
def manufacturing_stream(asset: str = "turbofan_engine", steps: int = 20):
    """
    Ordered sensor readings for the live-monitoring replay, each already scored
    (model + rules only: no Gemini call and nothing is saved), so the dashboard
    can draw the risk rising over time.
    """
    from manufacturing import data_ingestion, datasets, model_scoring

    if asset not in datasets.ASSETS:
        raise HTTPException(status_code=404, detail="Unknown asset.")

    readings = data_ingestion.replay_stream(asset, max(2, min(steps, 60)))
    out = []
    for reading in readings:
        scored = model_scoring.score("manufacturing", reading)
        out.append({
            "record": reading,
            "score": scored["score"],
            "overall_risk": scored["overall_risk"],
            "reason_codes": scored["reason_codes"],
        })
    return {"asset": asset, "readings": out}


@app.post("/api/agents/run")
async def run_agents(body: AgentRunRequest):
    """Run the four-agent chain (plain Python, or through Google ADK)."""
    from manufacturing import agents

    record = _resolve_manufacturing_record(body.record)
    try:
        if body.mode == "adk":
            state = await agents.run_adk_pipeline(record)
        else:
            state = await asyncio.to_thread(agents.run_pipeline, record)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail="Agent chain failed.") from e

    state.pop("record", None)
    state["mode"] = "adk" if body.mode == "adk" else "plain"
    return state


app.mount("/static", StaticFiles(directory=str(PUBLIC_DIR)), name="static")

if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)
