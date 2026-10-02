"""
Entrypoint for Cloud Run deployment.
Exposes the shared pipeline as HTTP endpoints, mirroring the Hatchable
JS prototype's api/ routes: /score, /records, /decisions, /health.

Local test:  python main.py        (then POST to http://localhost:8080/score)
Cloud Run:   this same file is what the Dockerfile runs.
"""
import os
from typing import Any, Dict, Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from shared.pipeline import run_pipeline
from bfsi.data_ingestion import list_all_records
from shared.state_store import list_decisions

from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse



app = FastAPI()


class ScoreRequest(BaseModel):
    domain: Optional[str] = "transaction"  # "transaction" or "loan"
    record: Dict[str, Any] = Field(default_factory=dict)



@app.get("/")
def index():
    return FileResponse("public/index.html")

@app.get("/health")
def health():
    decisions = list_decisions(limit=100000)
    return {
        "status": "ok",
        "service": "voice-first-fraud-risk-assistant",
        "persisted_decisions": len(decisions),
    }


@app.get("/api/records")
def records():
    return list_all_records()


@app.get("/api/decisions")
def decisions():
    return {"decisions": list_decisions(limit=100)}


@app.post("/api/score")
def score_record(body: ScoreRequest):
    domain = body.domain if body.domain == "loan" else "transaction"
    record = body.record
    if not record.get("id"):
        raise HTTPException(status_code=400, detail="A record id is required.")

    try:
        result = run_pipeline(domain, record)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail="Unable to score the record.") from e

app.mount("/static", StaticFiles(directory="public"), name="static")

if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)
