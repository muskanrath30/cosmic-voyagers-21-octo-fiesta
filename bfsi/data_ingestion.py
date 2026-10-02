"""
Serves transaction and loan sample records for the frontend's record list
(/api/records) and for local pipeline testing.

Both real datasets (paysim.csv, vehicle_loan.csv) are loaded into memory
ONCE, at import time -- not on every request. Every call to
list_all_records() then just samples from the already-loaded pools, mixing
in real fraud / default examples alongside normal ones, so a refresh on the
frontend shows a different, genuinely real set of records each time without
re-reading the CSVs from disk.

Column names are the real, confirmed ones (see shared/feature_engineering.py):
  - PaySim: amount, type, oldbalanceOrg, newbalanceOrig, nameDest,
    oldbalanceDest, newbalanceDest, isFraud (native PaySim columns)
  - Vehicle Loan: DISBURSED_AMOUNT, ASSET_COST, LTV, PERFORM_CNS_SCORE,
    PERFORM_CNS_SCORE_DESCRIPTION, PRI_*/SEC_* bureau fields,
    EMPLOYMENT_TYPE, DATE_OF_BIRTH, loan_default (target)
"""
import os

import pandas as pd

from bfsi.feature_engineering import _parse_duration_to_months, _age_from_dob

_DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
_PAYSIM_PATH = os.path.join(_DATA_DIR, "paysim.csv")
_LOAN_PATH = os.path.join(_DATA_DIR, "vehicle_loan.csv")

_N_FRAUD_SAMPLES = 2
_N_NORMAL_TXN_SAMPLES = 4
_N_DEFAULT_SAMPLES = 2
_N_NON_DEFAULT_SAMPLES = 4


def _load_transaction_pools():
    df = pd.read_csv(_PAYSIM_PATH)
    df = df[df["type"].isin(["TRANSFER", "CASH_OUT"])]
    fraud = df[df["isFraud"] == 1]
    normal = df[df["isFraud"] == 0]
    return fraud, normal


def _load_loan_pools():
    df = pd.read_csv(_LOAN_PATH)
    default = df[df["LOAN_DEFAULT"] == 1]
    non_default = df[df["LOAN_DEFAULT"] == 0]
    return default, non_default


print("[data_ingestion] Loading PaySim and Vehicle Loan datasets into memory ...")
_FRAUD_POOL, _NORMAL_POOL = _load_transaction_pools()
_DEFAULT_POOL, _NON_DEFAULT_POOL = _load_loan_pools()
print(
    f"[data_ingestion] Loaded {len(_FRAUD_POOL):,} fraud + {len(_NORMAL_POOL):,} "
    f"normal transactions, {len(_DEFAULT_POOL):,} default + "
    f"{len(_NON_DEFAULT_POOL):,} non-default loans."
)


def _transaction_row_to_record(row, idx) -> dict:
    return {
        "id": f"TXN-{idx:04d}",
        "type": row["type"],
        "amount": float(row["amount"]),
        "oldbalanceOrg": float(row["oldbalanceOrg"]),
        "newbalanceOrig": float(row["newbalanceOrig"]),
        "nameOrig": row["nameOrig"],
        "nameDest": row["nameDest"],
        "oldbalanceDest": float(row["oldbalanceDest"]),
        "newbalanceDest": float(row["newbalanceDest"]),
        "location": "N/A",
    }


def _loan_row_to_record(row, idx) -> dict:
    disbursed_amount = float(row["DISBURSED_AMOUNT"])
    return {
        "id": f"LOAN-{idx:04d}",
        "loanAmount": disbursed_amount,
        "disbursed_amount": disbursed_amount,
        "asset_cost": float(row["ASSET_COST"]),
        "ltv": float(row["LTV"]),
        "loanToValue": float(row["LTV"]),
        "perform_cns_score": float(row["PERFORM_CNS_SCORE"]) if pd.notna(row["PERFORM_CNS_SCORE"]) else 0.0,
        "perform_cns_score_description": row["PERFORM_CNS_SCORE_DESCRIPTION"],
        "pri_no_of_accts": float(row["PRI_NO_OF_ACCTS"]),
        "pri_active_accts": float(row["PRI_ACTIVE_ACCTS"]),
        "pri_overdue_accts": float(row["PRI_OVERDUE_ACCTS"]),
        "pri_current_balance": float(row["PRI_CURRENT_BALANCE"]),
        "pri_sanctioned_amount": float(row["PRI_SANCTIONED_AMOUNT"]),
        "pri_disbursed_amount": float(row["PRI_DISBURSED_AMOUNT"]),
        "sec_no_of_accts": float(row["SEC_NO_OF_ACCTS"]),
        "sec_active_accts": float(row["SEC_ACTIVE_ACCTS"]),
        "sec_overdue_accts": float(row["SEC_OVERDUE_ACCTS"]),
        "sec_current_balance": float(row["SEC_CURRENT_BALANCE"]),
        "new_accts_in_last_six_months": float(row["NEW_ACCTS_IN_LAST_SIX_MONTHS"]),
        "delinquent_accts_in_last_six_months": float(row["DELINQUENT_ACCTS_IN_LAST_SIX_MONTHS"]),
        "no_of_inquiries": float(row["NO_OF_INQUIRIES"]),
        "credit_history_length_months": _parse_duration_to_months(row["CREDIT_HISTORY_LENGTH"]),
        "average_acct_age_months": _parse_duration_to_months(row["AVERAGE_ACCT_AGE"]),
        "age_years": _age_from_dob(row["DATE_OF_BIRTH"]),
        "employmentType": row["EMPLOYMENT_TYPE"] if pd.notna(row["EMPLOYMENT_TYPE"]) else "Self employed",
        "location": "N/A",
    }


def list_all_records() -> dict:
    """Returns a FRESH random sample of real transactions and real loans on
    every call -- a mix of fraud/default and normal cases -- without
    re-reading the CSVs from disk. This is what /api/records calls."""
    fraud_sample = _FRAUD_POOL.sample(min(_N_FRAUD_SAMPLES, len(_FRAUD_POOL)))
    normal_sample = _NORMAL_POOL.sample(min(_N_NORMAL_TXN_SAMPLES, len(_NORMAL_POOL)))
    txn_rows = pd.concat([fraud_sample, normal_sample]).sample(frac=1)

    default_sample = _DEFAULT_POOL.sample(min(_N_DEFAULT_SAMPLES, len(_DEFAULT_POOL)))
    non_default_sample = _NON_DEFAULT_POOL.sample(min(_N_NON_DEFAULT_SAMPLES, len(_NON_DEFAULT_POOL)))
    loan_rows = pd.concat([default_sample, non_default_sample]).sample(frac=1)

    transactions = [
        _transaction_row_to_record(row, i + 1)
        for i, (_, row) in enumerate(txn_rows.iterrows())
    ]
    loans = [
        _loan_row_to_record(row, i + 1)
        for i, (_, row) in enumerate(loan_rows.iterrows())
    ]

    return {"transactions": transactions, "loans": loans}


if __name__ == "__main__":
    import json
    sample = list_all_records()
    print(json.dumps(sample, indent=2, default=str))