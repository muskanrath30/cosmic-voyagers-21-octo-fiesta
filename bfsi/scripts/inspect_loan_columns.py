"""
Run this FIRST on your Vehicle Loan Default CSV, before train_loan_model.py.
It just prints the columns and a sample row so we can confirm they match
what train_loan_model.py expects -- avoids wasting a training run on a
column-name mismatch.

    python scripts/inspect_loan_columns.py --input data/vehicle_loan.csv
"""
import argparse
import pandas as pd

parser = argparse.ArgumentParser()
parser.add_argument("--input", default="bfsi/data/vehicle_loan.csv")
args = parser.parse_args()

df = pd.read_csv(args.input)
print(f"Shape: {df.shape}")
print(f"\nColumns:\n{list(df.columns)}")
print(f"\nFirst row:\n{df.iloc[0]}")
print(f"\nMissing values:\n{df.isnull().sum()[df.isnull().sum() > 0]}")

# Common target column names across L&T Vehicle Loan Default mirrors
for candidate in ["loan_default", "Default", "default", "Loan_Default"]:
    if candidate in df.columns:
        print(f"\nTarget column found: '{candidate}'")
        print(df[candidate].value_counts(normalize=True) * 100)
        break
else:
    print("\nCould not auto-detect the target column -- find it manually in the column list above.")
