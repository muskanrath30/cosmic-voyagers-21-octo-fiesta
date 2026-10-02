"""
Stage 5: State & Visualization
Saves the final decision. Writes to Firestore if a project/emulator is
configured, otherwise falls back to printing (and keeping an in-memory
list) so this still works with zero cloud setup.
"""
import datetime
import uuid

try:
    from google.cloud import firestore
except ImportError:
    firestore = None

_mock_decisions = []  # in-memory fallback store, newest first
_client = None


def _get_client():
    global _client
    if firestore is None:
        return None
    if _client is None:
        try:
            _client = firestore.Client()
        except Exception:
            _client = None
    return _client


def save_decision(record: dict, domain: str, score_result: dict, explanation: str, action: str) -> dict:
    """Save a decision. Returns {id, created_at}."""
    decision_id = str(uuid.uuid4())
    created_at = datetime.datetime.utcnow().isoformat()

    doc = {
        "id": decision_id,
        "record_id": record.get("id"),
        "domain": domain,
        "record": record,
        "score": score_result.get("score"),
        "reason_code": score_result.get("reason_code"),
        "explanation": explanation,
        "action": action,
        "created_at": created_at,
    }

    client = _get_client()
    if client is not None:
        try:
            client.collection("decisions").document(decision_id).set(doc)
            return {"id": decision_id, "created_at": created_at}
        except Exception as e:
            print(f"[FIRESTORE WRITE FAILED, falling back to mock: {e}]")

    # Mock fallback: keep in memory + print, so this works with zero cloud setup
    _mock_decisions.insert(0, doc)
    print(f"[MOCK SAVE] {domain} {record.get('id')} -> action={action}, score={score_result.get('score')}")
    return {"id": decision_id, "created_at": created_at}


def list_decisions(limit: int = 100) -> list:
    """Return the most recent decisions, newest first."""
    client = _get_client()
    if client is not None:
        try:
            docs = (
                client.collection("decisions")
                .order_by("created_at", direction=firestore.Query.DESCENDING)
                .limit(limit)
                .stream()
            )
            return [d.to_dict() for d in docs]
        except Exception as e:
            print(f"[FIRESTORE READ FAILED, falling back to mock: {e}]")

    return _mock_decisions[:limit]
