"""
Stage 2: Model Scoring
Domain-specific. Uses the real trained models (models/fraud_model.joblib,
models/loan_model.joblib) when present. Falls back to the original
rule-based heuristic scorer when a model file isn't found -- so the
pipeline keeps working even before you've run the training scripts,
and keeps working for anyone who clones the repo without the model
files (they're gitignored -- large binary files).

Train the real models with:
    python scripts/train_fraud_model.py --input data/paysim.csv
    python scripts/train_loan_model.py  --input data/vehicle_loan.csv
"""
import json
import os

import joblib

from bfsi.feature_engineering import (
    engineer_transaction_features,
    engineer_loan_features,
    FRAUD_FEATURE_COLUMNS,
    LOAN_FEATURE_COLUMNS,
)

_MODELS_DIR = os.path.join(os.path.dirname(__file__), "models")

_fraud_model = None
_loan_model = None


def _load(domain: str):
    """Lazily load a trained model once, cache it. Returns None if not found."""
    global _fraud_model, _loan_model
    path = os.path.join(_MODELS_DIR, f"{'fraud' if domain == 'transaction' else 'loan'}_model.joblib")
    if domain == "transaction":
        if _fraud_model is None and os.path.exists(path):
            _fraud_model = joblib.load(path)
        return _fraud_model
    else:
        if _loan_model is None and os.path.exists(path):
            _loan_model = joblib.load(path)
        return _loan_model


# ---------- Heuristic fallback (original rule-based scorer) ----------

def _clamp(value: float) -> float:
    return max(0.0, min(0.99, value))


def _heuristic_score_transaction(r: dict) -> dict:
    score = 0.0
    reasons = []

    amount = r.get("amount", 0)
    if amount >= 100000:
        score += 0.32
        reasons.append("high transaction amount")
    elif amount >= 25000:
        score += 0.18
        reasons.append("elevated transaction amount")

    old_org = r.get("oldbalanceOrg", 0)
    new_org = r.get("newbalanceOrig", 0)
    balance_gap = abs((old_org - new_org) - amount)
    if balance_gap > max(500, amount * 0.08):
        score += 0.25
        reasons.append("origin balance movement is inconsistent with the transaction")

    if r.get("type") == "TRANSFER":
        score += 0.12
        reasons.append("transfer activity")
    if r.get("type") == "CASH_OUT":
        score += 0.10
        reasons.append("cash-out activity")

    if new_org <= max(1000, old_org * 0.05):
        score += 0.15
        reasons.append("origin account is nearly depleted after the transaction")

    old_dest = r.get("oldbalanceDest", 0)
    new_dest = r.get("newbalanceDest", 0)
    if (new_dest - old_dest) > 50000:
        score += 0.10
        reasons.append("destination balance has a large sudden increase")

    if r.get("location") in ["London"]:
        score += 0.08
        reasons.append("unusual cross-border location for this sample")

    score = _clamp(score)
    reason_code = (
        "HIGH_AMOUNT_AND_BALANCE_ANOMALY" if score >= 0.80 else
        "ELEVATED_TRANSFER_OR_CASHOUT_PATTERN" if score >= 0.50 else
        "LOW_RISK_TRANSACTION"
    )
    return {"score": round(score, 2), "reason_code": reason_code, "factors": reasons[:3], "model": "heuristic"}


def _heuristic_score_loan(r: dict) -> dict:
    score = 0.0
    reasons = []

    if not r.get("creditHistory", 1):
        score += 0.38
        reasons.append("limited or adverse credit history")

    ltv = r.get("loanToValue", r.get("ltv", 0))
    if ltv >= 90:
        score += 0.28
        reasons.append("very high loan-to-value ratio")
    elif ltv >= 80:
        score += 0.18
        reasons.append("high loan-to-value ratio")

    income = r.get("applicantIncome", 0)
    loan_amount = r.get("loanAmount", r.get("disbursed_amount", 0))
    income_multiple = loan_amount / max(income * 12, 1)
    if income_multiple > 1.5:
        score += 0.18
        reasons.append("loan size is high relative to annual income")
    elif income_multiple > 1.0:
        score += 0.10
        reasons.append("loan size is elevated relative to annual income")

    if r.get("employmentType") not in (None, "Salaried"):
        score += 0.08
        reasons.append("less stable employment type in this prototype")

    if 0 < income < 35000:
        score += 0.10
        reasons.append("lower applicant income")

    score = _clamp(score)
    reason_code = (
        "HIGH_LTV_AND_CREDIT_RISK" if score >= 0.80 else
        "ELEVATED_CREDIT_OR_AFFORDABILITY_RISK" if score >= 0.50 else
        "LOW_RISK_APPLICANT"
    )
    return {"score": round(score, 2), "reason_code": reason_code, "factors": reasons[:3], "model": "heuristic"}


# ---------- Real model scoring ----------

def _reason_from_score(score: float, high: str, mid: str, low: str) -> str:
    if score >= 0.80:
        return high
    if score >= 0.50:
        return mid
    return low


def _ml_score_transaction(model, r: dict) -> dict:
    features = engineer_transaction_features(r)
    row = [[features[col] for col in FRAUD_FEATURE_COLUMNS]]
    proba = float(model.predict_proba(row)[0][1])

    factors = []
    if features["errorBalanceOrig"] != 0 or features["errorBalanceDest"] != 0:
        factors.append("balance movement doesn't fully reconcile with the transaction amount")
    if features["amount"] >= 100000:
        factors.append("high transaction amount")
    if features["isTransfer"]:
        factors.append("transfer activity")
    if not factors:
        factors.append("model-identified pattern across balance and amount features")

    reason_code = _reason_from_score(
        proba, "HIGH_AMOUNT_AND_BALANCE_ANOMALY", "ELEVATED_TRANSFER_OR_CASHOUT_PATTERN", "LOW_RISK_TRANSACTION"
    )
    return {"score": round(proba, 4), "reason_code": reason_code, "factors": factors[:3], "model": "xgboost_paysim"}


def _ml_score_loan(model, r: dict) -> dict:
    features = engineer_loan_features(r)
    row = [[features[col] for col in LOAN_FEATURE_COLUMNS]]
    proba = float(model.predict_proba(row)[0][1])

    factors = []
    if features["ltv"] >= 80:
        factors.append("high loan-to-value ratio")
    if features["perform_cns_score"] and features["perform_cns_score"] < 650:
        factors.append("low bureau credit score")
    if features["delinquent_accts_in_last_six_months"] > 0:
        factors.append("recent delinquent accounts")
    if not factors:
        factors.append("model-identified pattern across credit bureau and loan features")

    reason_code = _reason_from_score(
        proba, "HIGH_LTV_AND_CREDIT_RISK", "ELEVATED_CREDIT_OR_AFFORDABILITY_RISK", "LOW_RISK_APPLICANT"
    )
    return {"score": round(proba, 4), "reason_code": reason_code, "factors": factors[:3], "model": "xgboost_vehicle_loan"}


# ---------- Public entrypoint ----------

def score(domain: str, record: dict) -> dict:
    """Score a record. domain is 'loan' or 'transaction'.
    Uses the real trained model if available, else the heuristic fallback."""
    model = _load(domain)

    if domain == "loan":
        if model is not None:
            try:
                return _ml_score_loan(model, record)
            except Exception as e:
                print(f"[ML scoring failed, falling back to heuristic: {e}]")
        return _heuristic_score_loan(record)

    if model is not None:
        try:
            return _ml_score_transaction(model, record)
        except Exception as e:
            print(f"[ML scoring failed, falling back to heuristic: {e}]")
    return _heuristic_score_transaction(record)
