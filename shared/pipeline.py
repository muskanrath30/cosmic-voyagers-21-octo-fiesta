"""
The Common Pipeline
Chains all five stages together. Stages 3, 4, 5 (Gemini reasoning, agent
decision, state store) are genuinely domain-agnostic and live in shared/.
Stages 1 and 2 (data ingestion, model scoring) are domain-specific and
live in bfsi/ -- manufacturing/ would add its own data_ingestion.py and
model_scoring.py with the same function signatures, and this file would
route to whichever domain's module the request needs.

Flow: Record -> Model Score -> Gemini Explanation -> Agent Decision -> Save
"""
from bfsi import data_ingestion, model_scoring
from shared import gemini_reasoning, agent_decision, state_store

# Domain -> which vertical's data_ingestion/model_scoring module to use.
# Both BFSI sub-domains (transaction fraud, loan risk) route to bfsi/.
# Add manufacturing domains here once that module exists, e.g.
# "sensor": manufacturing_model_scoring
_BFSI_DOMAINS = {"transaction", "loan"}


def run_pipeline(domain: str, input_record: dict) -> dict:
    """Runs a single record through all five stages.

    domain: "loan" or "transaction"
    input_record: either a full record dict, or {"id": "TXN-1001"} to
                   look up one of the sample records.
    """
    record = input_record
    if input_record.get("id") and len(input_record) == 1:
        looked_up = data_ingestion.get_record(domain, input_record["id"])
        if looked_up:
            record = looked_up

    score_result = model_scoring.score(domain, record)
    explanation = gemini_reasoning.explain(domain, record, score_result)
    action = agent_decision.decide_action(domain, score_result)
    saved = state_store.save_decision(record, domain, score_result, explanation, action)

    return {
        "decision_id": saved["id"],
        "created_at": saved["created_at"],
        "domain": domain,
        "record": record,
        "score": score_result,
        "explanation": explanation,
        "action": action,
    }


def run_pipeline_on_samples():
    """Runs every sample record (both domains) through the pipeline -- use for local testing."""
    results = []
    for domain in ("transaction", "loan"):
        for record in data_ingestion.get_sample_records(domain):
            result = run_pipeline(domain, record)
            results.append(result)
            print(
                f"[{domain}] {record.get('id')}: action={result['action']} "
                f"(score={result['score']['score']})"
            )
    return results


if __name__ == "__main__":
    run_pipeline_on_samples()
