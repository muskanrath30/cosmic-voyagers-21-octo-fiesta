"""
Manufacturing Stage 1: Data Ingestion

Loads sample machine sensor records for the Manufacturing pipeline.

The pipeline expects:
    get_record(domain, record_id)
    get_sample_records(domain)

Manufacturing currently uses the AI4I 2020 Predictive Maintenance
feature schema:
    Type
    Air temperature
    Process temperature
    Rotational speed
    Torque
    Tool wear
"""

import csv
import os


_DATA_DIR = os.path.join(
    os.path.dirname(__file__),
    "data",
)

_MACHINE_DATA_PATH = os.path.join(
    _DATA_DIR,
    "machine_data.csv",
)


def _load_machine_records() -> list[dict]:
    """Load the Manufacturing sample machine records."""

    records = []

    with open(
        _MACHINE_DATA_PATH,
        newline="",
        encoding="utf-8",
    ) as file:

        reader = csv.DictReader(file)

        for row in reader:
            records.append(
                {
                    "id": row["machine_id"],
                    "machine_id": row["machine_id"],
                    "Type": row["Type"],
                    "Air temperature": float(
                        row["Air temperature"]
                    ),
                    "Process temperature": float(
                        row["Process temperature"]
                    ),
                    "Rotational speed": float(
                        row["Rotational speed"]
                    ),
                    "Torque": float(
                        row["Torque"]
                    ),
                    "Tool wear": float(
                        row["Tool wear"]
                    ),
                }
            )

    return records


_MACHINE_RECORDS = _load_machine_records()


def get_sample_records(domain: str) -> list[dict]:
    """
    Return Manufacturing sample records.

    The domain argument is kept for compatibility with the
    shared pipeline interface.
    """

    if domain not in ("manufacturing", "sensor"):
        return []

    return _MACHINE_RECORDS.copy()


def get_record(domain: str, record_id: str) -> dict | None:
    """
    Look up one machine by ID.

    Example:
        get_record("manufacturing", "M004")
    """

    if domain not in ("manufacturing", "sensor"):
        return None

    for record in _MACHINE_RECORDS:

        if record["id"] == record_id:
            return record.copy()

    return None


def list_all_records() -> list[dict]:
    """Return all available Manufacturing sample records."""

    return _MACHINE_RECORDS.copy()


if __name__ == "__main__":

    print("=" * 80)
    print("MANUFACTURING DATA INGESTION TEST")
    print("=" * 80)

    records = get_sample_records("manufacturing")

    print(f"Loaded machines: {len(records)}")

    for record in records:
        print(
            f"{record['id']} | "
            f"Type={record['Type']} | "
            f"Temp={record['Process temperature']} | "
            f"RPM={record['Rotational speed']} | "
            f"Torque={record['Torque']} | "
            f"Tool wear={record['Tool wear']}"
        )