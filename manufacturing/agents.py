"""
Predictive Maintenance Copilot: the four-agent chain.

    Sensor Monitor -> Prediction -> Diagnosis (Gemini + RAG) -> Work Order

The plain-Python functions below are the SOURCE OF TRUTH. They are deterministic
except for the Gemini call in the Diagnosis step, and they are what the tests
and the shared pipeline use:

    run_pipeline(record) -> dict          # no ADK needed

The Google ADK agents are a thin orchestration shell around the same functions:

    build_adk_pipeline() -> SequentialAgent
    run_adk_pipeline(record) -> dict      # async

so an ADK version change can never take the demo down: if ADK is missing or
changes, call run_pipeline() instead.

Each step reads and writes a shared state dict:

    record -> monitor -> prediction -> diagnosis -> work_order
"""

from __future__ import annotations

import asyncio
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

if __package__ in (None, ""):  # allow `python agents.py`
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from manufacturing import cloud_store, config, datasets, gemini_reasoning, model_scoring
from manufacturing.preprocessing import InvalidRecordError

log = config.get_logger("agents")

_ACTION_BY_RISK = {
    "HIGH": "URGENT_INSPECTION",
    "MEDIUM": "SCHEDULE_INSPECTION",
    "LOW": "CONTINUE_MONITORING",
}


# --------------------------------------------------------------------------- #
# Step 1: Sensor Monitor
# --------------------------------------------------------------------------- #
def sensor_monitor(state: dict) -> dict:
    """Validate the reading and flag which sensors are out of their normal band."""

    record = state["record"]
    if not isinstance(record, dict):
        raise InvalidRecordError("record must be an object")

    asset = datasets.infer_asset(record)
    bundle = model_scoring._load_bundle(asset)
    from manufacturing import risk_rules

    codes = risk_rules.get_reason_codes(
        asset, record, bands=model_scoring._numeric_bands(bundle["bands"]))
    anomalous = codes != [risk_rules.NO_ANOMALY]

    return {"monitor": {
        "asset": asset,
        "id": record.get("id") or record.get("machine_id"),
        "out_of_band_codes": [] if not anomalous else codes,
        "anomaly_detected": anomalous,
    }}


# --------------------------------------------------------------------------- #
# Step 2: Prediction
# --------------------------------------------------------------------------- #
def prediction_step(state: dict) -> dict:
    """Run the asset model and the hybrid rules."""

    return {"prediction": model_scoring.score("manufacturing", state["record"])}


# --------------------------------------------------------------------------- #
# Step 3: Diagnosis (Gemini + RAG)
# --------------------------------------------------------------------------- #
def diagnosis_step(state: dict) -> dict:
    """Gemini explains the prediction using the retrieved manual sections."""

    prediction = state["prediction"]
    explanation, source = gemini_reasoning.generate_explanation(prediction)

    return {"diagnosis": {
        "explanation": explanation,
        "reasoning_source": source,
        "manual_sections": prediction.get("knowledge_sources", []),
    }}


# --------------------------------------------------------------------------- #
# Step 4: Work Order
# --------------------------------------------------------------------------- #
def decide(prediction: dict, reasoning_source: str) -> dict:
    """Decision object in the shared agent-stage format."""

    risk = prediction["overall_risk"]
    action = _ACTION_BY_RISK[risk]
    reasons = list(prediction["factors"])
    if reasoning_source == "LOCAL_FALLBACK":
        reasons.append("explanation generated locally (Gemini unavailable)")

    return {
        "action": action,
        "priority": risk,
        "summary": (
            f"{action}: {prediction['recommendation']} "
            f"(overall risk {risk}; ML {prediction['ml_risk']} / "
            f"sensor {prediction['sensor_risk']})."
        ),
        "reasons": reasons,
        "requires_human_review": risk != "LOW",
    }


def notify_technician(work_order: dict) -> None:
    """
    Notification hook. Currently writes a structured log entry; replace the body
    with Pub/Sub, e-mail or chat delivery without touching the callers.
    """

    log.info("technician notified", extra={"fields": {
        "work_order_id": work_order["work_order_id"],
        "asset": work_order["asset"],
        "priority": work_order["priority"],
    }})


def create_work_order(
    prediction: dict,
    explanation: str,
    reasoning_source: str,
    action: str | None = None,
) -> dict:
    """
    Decision + (for MEDIUM/HIGH risk) an idempotent work order, saved to
    Firestore and BigQuery when Google Cloud is configured.

    `action` lets the shared pipeline pass its own action name
    (e.g. urgent_maintenance_review) so both stages use one vocabulary.
    Returns {"decision", "work_order", "work_order_persisted"}.
    """

    decision = decide(prediction, reasoning_source)

    work_order = None
    persisted = False

    if decision["priority"] != "LOW":
        work_order = {
            "work_order_id": cloud_store.work_order_id(
                prediction["asset"], str(prediction.get("id")), decision["priority"]),
            "asset": prediction["asset"],
            "asset_name": prediction["asset_name"],
            "record_id": prediction.get("id"),
            "action": action or decision["action"],
            "priority": decision["priority"],
            "summary": decision["summary"],
            "reason_codes": prediction["reason_codes"],
            "explanation": explanation,
            "reasoning_source": reasoning_source,
            "status": "open",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        persisted = cloud_store.save_work_order(work_order)
        notify_technician(work_order)

    cloud_store.write_decision_rows(prediction, work_order)

    return {"decision": decision, "work_order": work_order,
            "work_order_persisted": persisted}


def work_order_step(state: dict) -> dict:
    """Agent step 4: decision, work order and notification."""

    return create_work_order(
        state["prediction"],
        state["diagnosis"]["explanation"],
        state["diagnosis"]["reasoning_source"],
    )


# --------------------------------------------------------------------------- #
# Plain pipeline (source of truth)
# --------------------------------------------------------------------------- #
_STEPS = [
    ("sensor_monitor", sensor_monitor),
    ("prediction", prediction_step),
    ("diagnosis", diagnosis_step),
    ("work_order", work_order_step),
]


def run_pipeline(record: dict) -> dict:
    """Run the four steps in order and return the accumulated state."""

    state: dict = {"record": record}
    for name, step in _STEPS:
        state.update(step(state))
    return state


# --------------------------------------------------------------------------- #
# Google ADK orchestration shell
# --------------------------------------------------------------------------- #
def build_adk_pipeline():
    """
    Build the four ADK agents as a SequentialAgent. Imports ADK lazily so the
    rest of the package works without it installed.
    """

    from google.adk.agents import BaseAgent, SequentialAgent
    from google.adk.events import Event, EventActions

    class StepAgent(BaseAgent):
        """Runs one deterministic step against session state."""

        step_name: str = ""

        async def _run_async_impl(self, ctx):
            step = dict(_STEPS)[self.step_name]
            delta = await asyncio.to_thread(step, dict(ctx.session.state))
            yield Event(author=self.name, actions=EventActions(state_delta=delta))

    agents = [
        StepAgent(name="SensorMonitorAgent", step_name="sensor_monitor",
                  description="Validates the reading and flags out-of-band sensors."),
        StepAgent(name="PredictionAgent", step_name="prediction",
                  description="Runs the asset's ML model and hybrid sensor rules."),
        StepAgent(name="DiagnosisAgent", step_name="diagnosis",
                  description="Gemini + RAG root-cause explanation."),
        StepAgent(name="WorkOrderAgent", step_name="work_order",
                  description="Creates the decision, work order and notification."),
    ]
    return SequentialAgent(
        name="PredictiveMaintenanceCopilot",
        sub_agents=agents,
        description="Sensor Monitor -> Prediction -> Diagnosis -> Work Order",
    )


async def run_adk_pipeline(record: dict) -> dict:
    """Run the ADK SequentialAgent for one record and return the final state."""

    from google.adk.runners import InMemoryRunner
    from google.genai import types

    app_name, user_id = "pm_copilot", "operator"
    runner = InMemoryRunner(agent=build_adk_pipeline(), app_name=app_name)
    session = await runner.session_service.create_session(
        app_name=app_name, user_id=user_id, state={"record": record})

    message = types.Content(role="user", parts=[types.Part(text="analyse reading")])
    async for _event in runner.run_async(
        user_id=user_id, session_id=session.id, new_message=message
    ):
        pass

    final = await runner.session_service.get_session(
        app_name=app_name, user_id=user_id, session_id=session.id)
    return dict(final.state)


if __name__ == "__main__":
    import json
    from manufacturing import data_ingestion

    demo = data_ingestion.get_record("manufacturing", "M004")
    mode = sys.argv[1] if len(sys.argv) > 1 else "plain"

    state = asyncio.run(run_adk_pipeline(demo)) if mode == "adk" else run_pipeline(demo)

    print(json.dumps(
        {k: v for k, v in state.items() if k != "record"}, indent=2, default=str))
