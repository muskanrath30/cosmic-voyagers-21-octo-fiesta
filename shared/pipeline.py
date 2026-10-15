"""
The Common Pipeline
Chains all five stages together. Stages 3, 4, 5 (Gemini reasoning, agent
decision, state store) are genuinely domain-agnostic and live in shared/.
Stages 1 and 2 (data ingestion, model scoring) are domain-specific and
route to the appropriate vertical module.

Flow: Record -> Model Score -> Gemini Explanation -> Agent Decision -> Save
"""

from shared import gemini_reasoning, agent_decision, state_store


# Domain -> which vertical's data_ingestion/model_scoring module to use.
# Existing BFSI domains remain unchanged.
_BFSI_DOMAINS = {"transaction", "loan"}
_MANUFACTURING_DOMAINS = {"manufacturing", "sensor"}


def _get_domain_modules(domain: str):
    """
    Load the appropriate domain-specific modules.

    Imports are intentionally lazy so Manufacturing can run locally
    without requiring the BFSI datasets to be present.
    """

    if domain in _BFSI_DOMAINS:
        from bfsi import data_ingestion, model_scoring
        return data_ingestion, model_scoring

    if domain in _MANUFACTURING_DOMAINS:
        from manufacturing import data_ingestion, model_scoring
        return data_ingestion, model_scoring

    raise ValueError(
        f"Unsupported domain: {domain}"
    )


def run_pipeline(domain: str, input_record: dict) -> dict:
    """Runs a single record through all five stages.

    domain:
        "loan", "transaction", or "manufacturing"

    input_record:
        either a full record dict, or {"id": "..."} to look up
        one of the sample records.
    """

    data_ingestion, model_scoring = _get_domain_modules(domain)

    record = input_record

    if input_record.get("id") and len(input_record) == 1:
        looked_up = data_ingestion.get_record(
            domain,
            input_record["id"],
        )

        if looked_up:
            record = looked_up

    score_result = model_scoring.score(
        domain,
        record,
    )

    is_manufacturing = domain in _MANUFACTURING_DOMAINS
    reasoning_source = None

    if is_manufacturing:
        explanation, reasoning_source = gemini_reasoning.explain_manufacturing(
            record,
            score_result,
        )
    else:
        explanation = gemini_reasoning.explain(
            domain,
            record,
            score_result,
        )

    action = agent_decision.decide_action(
        domain,
        score_result,
    )

    saved = state_store.save_decision(
        record,
        domain,
        score_result,
        explanation,
        action,
    )

    result = {
        "decision_id": saved["id"],
        "created_at": saved["created_at"],
        "domain": domain,
        "record": record,
        "score": score_result,
        "explanation": explanation,
        "action": action,
    }

    if is_manufacturing:
        # Manufacturing extras: which stage answered, which manual sections
        # grounded it, and the work order for MEDIUM/HIGH risk.
        from manufacturing import agents

        wo = agents.create_work_order(
            score_result,
            explanation,
            reasoning_source,
            action=action,
        )
        result["reasoning_source"] = reasoning_source
        result["manual_sections"] = score_result.get("knowledge_sources", [])
        result["work_order"] = wo["work_order"]
        result["work_order_persisted"] = wo["work_order_persisted"]

    return result


def run_pipeline_on_samples():
    """
    Runs sample records through the pipeline.

    BFSI behavior remains unchanged.
    Manufacturing samples are additionally supported.
    """

    results = []

    for domain in (
        "transaction",
        "loan",
        "manufacturing",
    ):
        data_ingestion, _ = _get_domain_modules(domain)

        for record in data_ingestion.get_sample_records(domain):
            result = run_pipeline(
                domain,
                record,
            )

            results.append(result)

            print(
                f"[{domain}] "
                f"{record.get('id')}: "
                f"action={result['action']} "
                f"(score={result['score']['score']})"
            )

    return results


if __name__ == "__main__":
    run_pipeline_on_samples()