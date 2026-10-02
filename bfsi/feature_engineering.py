"""
Shared feature-engineering logic for both domains.
Used by BOTH the training scripts (scripts/train_*.py) and the live
scoring path (shared/model_scoring.py) -- keeping this in one place
avoids train/serve skew (the #1 way these pipelines quietly break).
"""
import pandas as pd


# ---------- PaySim / transaction fraud ----------

FRAUD_FEATURE_COLUMNS = [
    "amount",
    "oldbalanceOrg",
    "newbalanceOrig",
    "oldbalanceDest",
    "newbalanceDest",
    "errorBalanceOrig",
    "errorBalanceDest",
    "isTransfer",  # 1 if type == TRANSFER, 0 if CASH_OUT
]


def engineer_transaction_features(record: dict) -> dict:
    """Build the exact feature set the fraud model was trained on,
    from a raw transaction record (PaySim-shaped fields)."""
    amount = float(record.get("amount", 0) or 0)
    old_org = float(record.get("oldbalanceOrg", 0) or 0)
    new_org = float(record.get("newbalanceOrig", 0) or 0)
    old_dest = float(record.get("oldbalanceDest", 0) or 0)
    new_dest = float(record.get("newbalanceDest", 0) or 0)
    txn_type = record.get("type", "")

    error_balance_orig = old_org - amount - new_org
    error_balance_dest = old_dest + amount - new_dest
    is_transfer = 1 if txn_type == "TRANSFER" else 0

    return {
        "amount": amount,
        "oldbalanceOrg": old_org,
        "newbalanceOrig": new_org,
        "oldbalanceDest": old_dest,
        "newbalanceDest": new_dest,
        "errorBalanceOrig": error_balance_orig,
        "errorBalanceDest": error_balance_dest,
        "isTransfer": is_transfer,
    }


def engineer_transaction_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """Same logic as engineer_transaction_features, vectorised for training."""
    out = pd.DataFrame()
    out["amount"] = df["amount"]
    out["oldbalanceOrg"] = df["oldbalanceOrg"]
    out["newbalanceOrig"] = df["newbalanceOrig"]
    out["oldbalanceDest"] = df["oldbalanceDest"]
    out["newbalanceDest"] = df["newbalanceDest"]
    out["errorBalanceOrig"] = df["oldbalanceOrg"] - df["amount"] - df["newbalanceOrig"]
    out["errorBalanceDest"] = df["oldbalanceDest"] + df["amount"] - df["newbalanceDest"]
    out["isTransfer"] = (df["type"] == "TRANSFER").astype(int)
    return out[FRAUD_FEATURE_COLUMNS]


# ---------- Vehicle Loan Default ----------
# Based on the standard L&T Vehicle Loan Default Prediction schema
# (disbursed_amount, asset_cost, ltv, PERFORM_CNS.SCORE, PRI.* / SEC.*
# bureau fields, AVERAGE.ACCT.AGE / CREDIT.HISTORY.LENGTH as "Xyrs Ymon"
# strings, Employment.Type, Date.of.Birth, DisbursalDate).
# CONFIRM your actual CSV's columns match before relying on this --
# run scripts/inspect_loan_columns.py first if unsure.

LOAN_FEATURE_COLUMNS = [
    "disbursed_amount",
    "asset_cost",
    "ltv",
    "perform_cns_score",
    "has_bureau_history",
    "bureau_risk_tier",
    "pri_no_of_accts",
    "pri_active_accts",
    "pri_overdue_accts",
    "pri_current_balance",
    "pri_sanctioned_amount",
    "pri_disbursed_amount",
    "sec_no_of_accts",
    "sec_active_accts",
    "sec_overdue_accts",
    "sec_current_balance",
    "new_accts_in_last_six_months",
    "delinquent_accts_in_last_six_months",
    "no_of_inquiries",
    "credit_history_length_months",
    "average_acct_age_months",
    "age_years",
    "is_salaried",
]

# Ordinal risk tier derived from PERFORM_CNS_SCORE_DESCRIPTION's letter grade.
# 0 = lowest risk ... 4 = highest risk, 5 = not scored (various reasons),
# 6 = no bureau history at all. This captures real signal that the raw
# PERFORM_CNS_SCORE misses, since ~50% of records have score=0 for a mix
# of "genuinely no history" and "not scored" reasons -- conflating all of
# those with "score of 0 = great credit" was hurting the model.
_BUREAU_RISK_TIER_MAP = {
    "A-Very Low Risk": 0, "B-Very Low Risk": 0, "C-Very Low Risk": 0, "D-Very Low Risk": 0,
    "E-Low Risk": 1, "F-Low Risk": 1, "G-Low Risk": 1,
    "H-Medium Risk": 2, "I-Medium Risk": 2,
    "J-High Risk": 3, "K-High Risk": 3,
    "L-Very High Risk": 4, "M-Very High Risk": 4,
    "No Bureau History Available": 6,
}
# Everything starting with "Not Scored" (several variants) -> tier 5
_DEFAULT_RISK_TIER_NOT_SCORED = 5
_DEFAULT_RISK_TIER_UNKNOWN = 3  # fallback for anything unrecognised -- treat as medium


def _bureau_risk_tier(description) -> int:
    if pd.isna(description):
        return _DEFAULT_RISK_TIER_UNKNOWN
    text = str(description)
    if text in _BUREAU_RISK_TIER_MAP:
        return _BUREAU_RISK_TIER_MAP[text]
    if text.startswith("Not Scored"):
        return _DEFAULT_RISK_TIER_NOT_SCORED
    return _DEFAULT_RISK_TIER_UNKNOWN


def _has_bureau_history(description) -> int:
    if pd.isna(description):
        return 0
    text = str(description)
    if text == "No Bureau History Available" or text.startswith("Not Scored"):
        return 0
    return 1


def _parse_duration_to_months(value) -> float:
    """Parses strings like '4yrs 3mon' into total months. Returns 0 if unparseable."""
    if pd.isna(value):
        return 0.0
    try:
        text = str(value)
        years = 0
        months = 0
        if "yrs" in text:
            years = int(text.split("yrs")[0].strip())
            text = text.split("yrs")[1]
        if "mon" in text:
            months = int(text.replace("mon", "").strip())
        return years * 12 + months
    except Exception:
        return 0.0


def _age_from_dob(dob_str, reference_date=None) -> float:
    """Age in years from a Date.of.Birth string (dd-mm-yyyy expected)."""
    if pd.isna(dob_str):
        return 0.0
    try:
        dob = pd.to_datetime(dob_str, dayfirst=True, errors="coerce")
        if pd.isna(dob):
            return 0.0
        ref = pd.to_datetime(reference_date) if reference_date else pd.Timestamp.now()
        return round((ref - dob).days / 365.25, 1)
    except Exception:
        return 0.0


def engineer_loan_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """Vectorised feature engineering for the Vehicle Loan Default training set.
    Column names confirmed against the real L&T dataset (uppercase + underscores,
    e.g. PRI_NO_OF_ACCTS, not PRI.NO.OF.ACCTS)."""
    out = pd.DataFrame()
    out["disbursed_amount"] = df["DISBURSED_AMOUNT"]
    out["asset_cost"] = df["ASSET_COST"]
    out["ltv"] = df["LTV"]
    out["perform_cns_score"] = pd.to_numeric(df["PERFORM_CNS_SCORE"], errors="coerce").fillna(0)
    out["has_bureau_history"] = df["PERFORM_CNS_SCORE_DESCRIPTION"].apply(_has_bureau_history)
    out["bureau_risk_tier"] = df["PERFORM_CNS_SCORE_DESCRIPTION"].apply(_bureau_risk_tier)
    out["pri_no_of_accts"] = df["PRI_NO_OF_ACCTS"]
    out["pri_active_accts"] = df["PRI_ACTIVE_ACCTS"]
    out["pri_overdue_accts"] = df["PRI_OVERDUE_ACCTS"]
    out["pri_current_balance"] = df["PRI_CURRENT_BALANCE"]
    out["pri_sanctioned_amount"] = df["PRI_SANCTIONED_AMOUNT"]
    out["pri_disbursed_amount"] = df["PRI_DISBURSED_AMOUNT"]
    out["sec_no_of_accts"] = df["SEC_NO_OF_ACCTS"]
    out["sec_active_accts"] = df["SEC_ACTIVE_ACCTS"]
    out["sec_overdue_accts"] = df["SEC_OVERDUE_ACCTS"]
    out["sec_current_balance"] = df["SEC_CURRENT_BALANCE"]
    out["new_accts_in_last_six_months"] = df["NEW_ACCTS_IN_LAST_SIX_MONTHS"]
    out["delinquent_accts_in_last_six_months"] = df["DELINQUENT_ACCTS_IN_LAST_SIX_MONTHS"]
    out["no_of_inquiries"] = df["NO_OF_INQUIRIES"]
    out["credit_history_length_months"] = df["CREDIT_HISTORY_LENGTH"].apply(_parse_duration_to_months)
    out["average_acct_age_months"] = df["AVERAGE_ACCT_AGE"].apply(_parse_duration_to_months)
    out["age_years"] = df["DATE_OF_BIRTH"].apply(_age_from_dob)
    # EMPLOYMENT_TYPE has ~7,661 missing values and uses "Self employed" (no hyphen)
    out["is_salaried"] = (df["EMPLOYMENT_TYPE"] == "Salaried").astype(int)
    return out[LOAN_FEATURE_COLUMNS].fillna(0)


def engineer_loan_features(record: dict) -> dict:
    """Build the loan feature set from a raw record at inference time.
    Expects the same field names as the prototype's loan records (camelCase)
    OR the raw L&T column names -- handles both so your existing dummy
    records and a real applicant form both work."""

    def pick(*keys, default=0):
        for k in keys:
            if k in record and record[k] is not None:
                return record[k]
        return default

    disbursed_amount = float(pick("disbursed_amount", "loanAmount", default=0))
    asset_cost = float(pick("asset_cost", default=disbursed_amount / 0.8 if disbursed_amount else 0))
    ltv = float(pick("ltv", "loanToValue", default=0))
    perform_cns_score = float(pick("perform_cns_score", "PERFORM_CNS.SCORE", default=0) or 0)
    bureau_description = pick("perform_cns_score_description", "PERFORM_CNS.SCORE.DESCRIPTION", default=None)

    return {
        "disbursed_amount": disbursed_amount,
        "asset_cost": asset_cost,
        "ltv": ltv,
        "perform_cns_score": perform_cns_score,
        "has_bureau_history": _has_bureau_history(bureau_description) if bureau_description else (1 if perform_cns_score > 0 else 0),
        "bureau_risk_tier": _bureau_risk_tier(bureau_description) if bureau_description else _DEFAULT_RISK_TIER_UNKNOWN,
        "pri_no_of_accts": float(pick("pri_no_of_accts", default=0)),
        "pri_active_accts": float(pick("pri_active_accts", default=0)),
        "pri_overdue_accts": float(pick("pri_overdue_accts", default=0)),
        "pri_current_balance": float(pick("pri_current_balance", default=0)),
        "pri_sanctioned_amount": float(pick("pri_sanctioned_amount", default=0)),
        "pri_disbursed_amount": float(pick("pri_disbursed_amount", default=0)),
        "sec_no_of_accts": float(pick("sec_no_of_accts", default=0)),
        "sec_active_accts": float(pick("sec_active_accts", default=0)),
        "sec_overdue_accts": float(pick("sec_overdue_accts", default=0)),
        "sec_current_balance": float(pick("sec_current_balance", default=0)),
        "new_accts_in_last_six_months": float(pick("new_accts_in_last_six_months", default=0)),
        "delinquent_accts_in_last_six_months": float(pick("delinquent_accts_in_last_six_months", default=0)),
        "no_of_inquiries": float(pick("no_of_inquiries", default=0)),
        "credit_history_length_months": float(pick("credit_history_length_months", default=0)),
        "average_acct_age_months": float(pick("average_acct_age_months", default=0)),
        "age_years": float(pick("age_years", default=35)),
        "is_salaried": 1 if pick("employmentType", "is_salaried", default="Salaried") in ("Salaried", 1, True) else 0,
    }
