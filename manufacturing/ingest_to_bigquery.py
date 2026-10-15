"""
Load raw sensor readings into BigQuery (table raw_sensor_readings).

    python -m manufacturing.ingest_to_bigquery --asset turbofan_engine --limit 20000
    python -m manufacturing.ingest_to_bigquery --asset metro_compressor --limit 0   # all local rows

Rows are written in the long format defined in bigquery_schema.sql
(device_id, sensor_id, value, recorded_at) using a batch LOAD job, which is not
subject to streaming-insert limits and fails loudly if the schema is wrong.

The local metropt_sample.csv is a sample. To load the complete MetroPT-3 file
use `bq load` with the original CSV, or point --csv at it.

Requires GOOGLE_CLOUD_PROJECT and BIGQUERY_DATASET, and the tables created by:
    bq query --use_legacy_sql=false < manufacturing/bigquery_schema.sql
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd

from manufacturing import config, datasets

BATCH = 50_000


def to_long(asset: str, df: pd.DataFrame) -> list[dict]:
    """Wide training frame -> long rows matching raw_sensor_readings."""

    feats = datasets.feature_columns(asset)
    now = datetime.now(timezone.utc)
    rows = []

    for i, (_, r) in enumerate(df.iterrows()):
        if "timestamp" in df.columns and pd.notna(r.get("timestamp")):
            at = pd.Timestamp(r["timestamp"]).tz_localize("UTC") \
                if pd.Timestamp(r["timestamp"]).tzinfo is None else pd.Timestamp(r["timestamp"])
        else:
            at = now - timedelta(seconds=len(df) - i)

        if "unit" in df.columns:
            device = f"{asset}:{r['unit']}"
        else:
            device = f"{asset}:{i // 100:05d}"

        for feat in feats:
            rows.append({
                "reading_id": uuid.uuid4().hex,
                "device_id": device,
                "sensor_id": feat,
                "sensor_type": asset,
                "value": float(r[feat]),
                "recorded_at": at.isoformat(),
                "metadata": json.dumps({"dataset": datasets.get_spec(asset)["dataset"]}),
            })
    return rows


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--asset", default="turbofan_engine", choices=list(datasets.ASSETS))
    ap.add_argument("--limit", type=int, default=20000, help="0 = all local rows")
    ap.add_argument("--csv", help="load this CSV instead of the local training frame")
    args = ap.parse_args()

    if not config.gcp_available():
        sys.exit("Set GOOGLE_CLOUD_PROJECT (and BIGQUERY_DATASET) first.")

    df = pd.read_csv(args.csv) if args.csv else datasets.load_training_frame(args.asset)
    if args.limit:
        df = df.head(args.limit)

    from google.cloud import bigquery
    client = bigquery.Client(project=config.PROJECT_ID)
    table_id = f"{config.PROJECT_ID}.{config.BIGQUERY_DATASET}.raw_sensor_readings"
    job_config = bigquery.LoadJobConfig(
        write_disposition="WRITE_APPEND",
        source_format=bigquery.SourceFormat.NEWLINE_DELIMITED_JSON,
    )

    total = 0
    for start in range(0, len(df), BATCH // len(datasets.feature_columns(args.asset)) or 1):
        chunk = df.iloc[start:start + BATCH // len(datasets.feature_columns(args.asset))]
        rows = to_long(args.asset, chunk)
        client.load_table_from_json(rows, table_id, job_config=job_config).result()
        total += len(rows)
        print(f"loaded {total} readings ...")

    print(f"asset={args.asset} source_rows={len(df)} readings_written={total} -> {table_id}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
