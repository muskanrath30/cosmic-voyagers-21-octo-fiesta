# Manufacturing track: Predictive Maintenance Copilot

Drop-in replacement for the `manufacturing/` package. Original file names and
the shared-pipeline contract are kept; `shared/`, `public/`, `bfsi/` and
`main.py` are not touched.

```
score(domain, record)              model_scoring.py   (same signature)
get_record / get_sample_records    data_ingestion.py  (same signatures)
generate_explanation(prediction)   gemini_reasoning.py
retrieve_knowledge(reason_codes)   rag_retriever.py
```

## What changed, file by file

| Original file | Now |
|---|---|
| `model_scoring.py` | Same `score()` contract. Routes to one of four assets, validates input, adds RUL for turbofans, returns the manual sections used. Heuristic fallback is flagged `degraded: true`. |
| `data_ingestion.py` | Same functions. Adds deterministic samples for the new assets and `replay_stream()` for live-monitoring demos. |
| `gemini_reasoning.py` | Vertex AI or API-key client, timeout, retry, circuit breaker, prompt sanitising, one JSON log line per call with `reasoning_source`. |
| `rag_retriever.py` | Section-based retrieval ranked by matching reason codes, plus `retrieve_sections()` for the UI. |
| `knowledge/maintenance_manual.txt` | Rewritten in sections with `Codes:` lines, now covering all four assets. |
| `train.py` | One trainer for every asset. Grouped split, threshold chosen on validation, ML vs rules vs hybrid comparison, RUL model for turbofans. Saves to `models/` (the old `model/` vs `models/` mismatch is gone). |
| `predict.py`, `batch_predict.py` | Thin wrappers over `model_scoring`, so scoring logic exists once. |
| `threshold_analysis.py` | Per asset; sweeps on validation, shows test once. |
| `preprocessing.py` | AI4I cleaning kept; adds record validation. |
| `download_dataset.py` | Unchanged (AI4I). |
| **New** `config.py`, `datasets.py`, `risk_rules.py` | Env config + logging, asset registry and loaders, reason codes and risk fusion. |
| **New** `agents.py` | Sensor Monitor, Prediction, Diagnosis, Work Order: plain Python plus a Google ADK `SequentialAgent` shell. |
| **New** `cloud_store.py`, `ingest_to_bigquery.py`, `bigquery_schema.sql` | Firestore work orders and BigQuery rows that match the schema. |
| **New** `fetch_datasets.py`, `tests/` | Real-data download, 30+ tests. |

Assets: `machine_tool` (AI4I, the original), `metro_compressor` (MetroPT-3),
`turbofan_engine` (NASA C-MAPSS), `bearing` (CWRU). Records without an `asset`
key that use the AI4I fields are treated as `machine_tool`, so existing calls
keep working.

## Risk logic (changed on purpose)

The old rule "overall risk is the more severe of ML and sensor risk" let any
noisy rule raise a HIGH alert. Now:

| ML risk | Sensor risk | Overall |
|---|---|---|
| HIGH | any | HIGH |
| MEDIUM | MEDIUM or HIGH | HIGH |
| MEDIUM | LOW | MEDIUM |
| LOW | HIGH | MEDIUM (investigate, do not alarm) |
| LOW | LOW or MEDIUM | LOW |

`LOW_ROTATIONAL_SPEED` (about 1 in 5 healthy AI4I rows) and the derived
`HIGH_MECHANICAL_LOAD` no longer count toward the sensor-warning total. The ML
HIGH threshold is the validation-chosen operating threshold, MEDIUM is half of it.
Sensor bands for the other assets come from healthy training rows, not hand-set numbers.

## Run locally (from the repository root)

```bash
pip install -r manufacturing/requirements-local.txt

python manufacturing/download_dataset.py          # AI4I (optional legacy asset)
python -m manufacturing.fetch_datasets            # real MetroPT-3 + CWRU (needs internet)
python -m manufacturing.train                     # trains every asset that has data
python -m manufacturing.batch_predict --no-llm    # scores all sample records
python -m manufacturing.predict --id TF-001
python -m manufacturing.agents plain              # 4-agent chain, plain Python
python -m manufacturing.agents adk                # same chain through ADK
pytest manufacturing/tests -q
```

`fetch_datasets.py` prints plainly if a download fails. Without it the metro and
bearing assets train on synthetic stand-ins, and `metrics.json` records
`"data_source": "synthetic_standin"`. Say which data is real in the deck.
For C-MAPSS FD002 to FD004, place the NASA `train_FD00x.txt` files in
`data/samples/` and retrain.

Sample IDs: `M001..M010` (CNC), `MC-###` (compressor), `TF-###` (turbofan),
`BR-###` (bearing).

## Gemini

```bash
export GOOGLE_API_KEY=...                 # local (Developer API)
# or, on Google Cloud (no key):
export GOOGLE_CLOUD_PROJECT=your-project
export GOOGLE_GENAI_USE_VERTEXAI=true
export GOOGLE_CLOUD_LOCATION=us-central1  # location that serves your model
export GEMINI_MODEL_NAME=<a model your project can call>

python -m manufacturing.gemini_reasoning  # exits 0 only if the call really used Gemini
```

The default model name `gemini-3.8-flash` was inherited from the original code
and could not be verified from here. Run the command above before relying on it.
If `reasoning_source` is `LOCAL_FALLBACK`, the log line says why (`no_credentials`,
`call_failed`, `circuit_open`, `sdk_missing`).

## Google Cloud setup

Services: Cloud Run (hosts the existing app), Firestore, BigQuery, Vertex AI
(Gemini), Cloud Storage (optional model artifacts).

```bash
export PROJECT=your-project REGION=us-central1
gcloud config set project $PROJECT
gcloud services enable run.googleapis.com firestore.googleapis.com bigquery.googleapis.com \
  aiplatform.googleapis.com storage.googleapis.com artifactregistry.googleapis.com cloudbuild.googleapis.com
gcloud firestore databases create --location=$REGION

# BigQuery tables (replace the dataset name inside the file if you change it)
bq mk --dataset $PROJECT:pm_platform
bq query --use_legacy_sql=false < manufacturing/bigquery_schema.sql

# service account roles for the Cloud Run identity (least privilege)
SA=$(gcloud projects describe $PROJECT --format='value(projectNumber)')-compute@developer.gserviceaccount.com
for R in roles/datastore.user roles/bigquery.dataEditor roles/bigquery.jobUser roles/aiplatform.user; do
  gcloud projects add-iam-policy-binding $PROJECT --member=serviceAccount:$SA --role=$R
done

# load readings
python -m manufacturing.ingest_to_bigquery --asset turbofan_engine --limit 20000
```

Environment for the Cloud Run service:

```
GOOGLE_CLOUD_PROJECT=<project>   GOOGLE_GENAI_USE_VERTEXAI=true
GOOGLE_CLOUD_LOCATION=<region>   GEMINI_MODEL_NAME=<model>
BIGQUERY_DATASET=pm_platform     PM_STRICT_CONFIG=true
```

Deploy with your existing root Dockerfile and deploy script. Two things to add:

1. Train at image build so models are baked in:
   `RUN python -c "from manufacturing.train import ensure_models; ensure_models()"`
   (needs the data files inside the image; the bundled FD001 file is enough for the turbofan).
2. Put limits on the service, since the endpoint is public and calls Gemini:
   `--max-instances 3 --min-instances 1 --timeout 60` (set min back to 0 after judging),
   and add a budget alert in Billing.

`PM_STRICT_CONFIG=true` makes `config.validate()` raise at startup if the
project, Gemini credentials or models are missing, instead of silently falling
back. Call `config.validate()` from your app startup to use it.

## Using it inside the repo

Checked against the updated repo: with this folder in place, `run_pipeline("manufacturing", {"id": "TF-001"})` and all 28 sample records go through `shared/pipeline.py` unchanged
(`urgent_maintenance_review` / `schedule_maintenance` / `continue_monitoring`).
The `model/` to `models/` fix is already how this package works (train, predict, scoring all use `models/`).

These items live outside `manufacturing/`, so they are listed here, not applied:

1. **requirements.txt**: add `google-genai`, `scipy` and (for the agent chain) `google-adk`.
2. **Dockerfile**: `.gitignore` excludes `manufacturing/models/*.joblib` and
   `manufacturing/data/*.csv`, so the image has no trained models unless it builds them.
   After `COPY . .` add:
   ```
   RUN python manufacturing/download_dataset.py || echo "AI4I download skipped"
   RUN python -c "from manufacturing.train import ensure_models; print(ensure_models())"
   ```
   Commit `manufacturing/data/samples/metropt_sample.csv` and `cwru_sample.npz` after running
   `fetch_datasets.py` (they are not git-ignored), so the image trains on real data.
   Without `ai4i2020.csv` the ten `M001..M010` machines are scored by the heuristic and flagged `degraded`.
3. **shared/gemini_reasoning.py** still uses the old `google.generativeai` SDK with `gemini-1.5-flash`
   and an API key only, so on Cloud Run it will fall back to the mock text. For manufacturing, delegate
   to this package at the top of `explain()`:
   ```python
   if domain in ("manufacturing", "sensor"):
       from manufacturing.gemini_reasoning import generate_explanation
       text, source = generate_explanation(score_result)
       return text if source == "GEMINI" else f"[{source}] " + text
   ```
4. **main.py**: `/api/score` forces any domain except `loan` to `transaction`, `/api/records` returns BFSI
   records only, and `public/` has no manufacturing mode. Until that is changed, manufacturing runs only via
   `shared.pipeline.run_pipeline`. Minimal change:
   `domain = body.domain if body.domain in ("loan", "manufacturing") else "transaction"`, plus a
   `/api/records?domain=manufacturing` branch returning `manufacturing.data_ingestion.list_all_records()`.

## What was tested, and what was not

Tested in a sandbox: training and scoring for all four assets, grouped split,
validation-chosen thresholds, risk fusion, validation errors, RAG, Gemini retry
and circuit breaker (with a fake client), work-order idempotency, and the ADK
chain on `google-adk` 2.11.0 (matches the plain pipeline). 32 tests pass.

Not tested: real Gemini or Vertex calls (no credentials there), the MetroPT-3 and
CWRU downloads (blocked there), the real AI4I file (the code path was tested on a
generated stand-in), and any Google Cloud write. Expect to fix small things the
first time you run those. `SequentialAgent` is marked deprecated in ADK 2.x in
favour of `Workflow`; it works, and `agents.py` is the only file to change if
you move.

## Known limits

- The alert threshold maximises F1 on validation (`--beta 2` favours recall).
- C-MAPSS is a simulation, not field data. CWRU is a lab rig with seeded faults.
- `notify_technician()` writes a log entry. Replace its body with Pub/Sub or e-mail.
- MetroPT-3 splits are grouped by hour only when the sample has timestamps (the fetch script writes them). CWRU windows come from just 5 recordings, so the split is stratified random and CWRU scores are optimistic: neighbouring windows of one recording can land in both train and test.
  source column (the fetch script writes them); otherwise stratified random.
- Live streaming (Pub/Sub, Dataflow), a model registry, drift monitoring and CI/CD
  are not included. Name them as next steps.
