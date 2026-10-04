from pathlib import Path

from ucimlrepo import fetch_ucirepo


ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
OUTPUT_FILE = DATA_DIR / "ai4i2020.csv"


def main():
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    print("Downloading AI4I 2020 Predictive Maintenance Dataset...")
    print()

    dataset = fetch_ucirepo(id=601)

    features = dataset.data.features.copy()
    targets = dataset.data.targets.copy()

    dataframe = features.copy()

    for column in targets.columns:
        dataframe[column] = targets[column]

    dataframe.to_csv(OUTPUT_FILE, index=False)

    print("Dataset downloaded successfully.")
    print(f"File: {OUTPUT_FILE}")
    print(f"Rows: {len(dataframe)}")
    print(f"Columns: {len(dataframe.columns)}")
    print()
    print("Columns:")
    for column in dataframe.columns:
        print(f"  - {column}")


if __name__ == "__main__":
    main()