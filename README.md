# Predictive Maintenance Copilot

**Team Cosmic Voyagers · AI Builder Cup 2026 · Manufacturing: Intelligent Operations & Industrial Efficiency**

Sensor readings in, failure risk out. The copilot combines an ML failure prediction with
sensor-band rules, asks Gemini for a plain-language diagnosis grounded in a maintenance
manual (with the manual sections shown), and creates a work order. A four-agent chain
(Google ADK) runs the same flow step by step, and the UI supports voice questions and a live
sensor replay.

- Live app: `<Cloud Run URL>`
- Demo video: `<video link>`
- Deck: `<deck link>`

---

## Problem statement

**Theme:** Manufacturing: Intelligent Operations & Industrial Efficiency. AI should turn operational data into meaningful insights, recommendations, or actions.

**The problem.** Unplanned equipment downtime is one of the costliest problems in manufacturing and industrial operations. Plants already collect large volumes of sensor data, but maintenance teams still face three gaps:

1. **Noisy alerts.** Fixed sensor thresholds fire constantly, so real warnings get ignored.
2. **Unexplained predictions.** A bare "failure probability" gives a technician nothing to act on.
3. **Slow follow-through.** Even when a risk is spotted, turning it into a documented work order is manual, and the knowledge in maintenance manuals is rarely at hand.

**Our solution.** A copilot that predicts failure risk per machine, cross-checks it against sensor behaviour learned from healthy data, explains the result in plain language using the plant's own maintenance manual, and creates the work order, so a technician can go from sensor reading to action in one screen.

**Who benefits.** Maintenance technicians and plant supervisors (faster, better-informed decisions), and the plant itself (fewer unplanned stoppages, safer and more efficient operations).

---

## What we built

| Capability | How it is done |
|---|---|
| Failure prediction | One trained model per asset type (random forest), with a validation-chosen alert threshold. Turbofan engines also get a remaining-useful-life estimate. |
| Sensor-aware risk | Sensor bands learned from healthy training data raise reason codes. An explicit rule fuses ML risk and sensor risk (table below). |
| Grounded explanation (RAG) | A section-based maintenance manual is retrieved by reason code; Gemini writes the diagnosis and cites the sections used. The UI lists them. |
| Reliable Gemini calls | Timeout, one retry, circuit breaker, prompt sanitising, and a local fallback explanation so the UI never shows a server error. |
| Agentic workflow | Sensor Monitor, Prediction, Diagnosis, Work Order agents, runnable in plain Python or through Google ADK (identical decisions). |
| Work orders | Idempotent id per machine, risk and day; saved to Firestore. |
| User interface | One dashboard: machine list, risk and remaining life, manual sources, work order, agent-chain button, live sensor replay, and voice questions. |
| Cloud deployment | Containerised FastAPI app on Cloud Run, Firestore for state, Gemini for reasoning. |
| Quality | 34 automated tests, structured JSON logs, a `/health` endpoint with model status and Gemini fallback rate, a rate limit and an instance cap. |

### Technology used

| Layer | Technology |
|---|---|
| Generative AI | Google Gemini (`gemini-3.1-flash-lite`) via the `google-genai` SDK (API key locally; Vertex AI supported) |
| Agents | Google Agent Development Kit (ADK), `SequentialAgent` over four agents |
| Retrieval | Section-based retrieval over `maintenance_manual.txt`, ranked by matching reason codes |
| ML | scikit-learn (random forest, grouped train/validation/test split), pandas, SciPy |
| Backend | Python 3.12, FastAPI, Uvicorn |
| Frontend | HTML, CSS, JavaScript; browser speech recognition and text-to-speech for voice |
| Google Cloud | Cloud Run, Cloud Build, Artifact Registry, Firestore, Vertex AI (optional), Cloud Logging |
| Data | AI4I 2020, MetroPT-3, NASA C-MAPSS FD001, CWRU Bearing |

### Architecture

```
                         ┌────────────────────────────────────────────┐
  User ──▶ │  Dashboard (public/)  +  voice questions   │
                         └───────────────────┬────────────────────────┘
                                             │ HTTPS
                                  ┌──────────▼───────────┐
                                  │ FastAPI  (main.py)   │  Cloud Run
                                  │ rate limit · /health │
                                  └──────────┬───────────┘
                          ┌──────────────────┴───────────────────┐
                          │                                      │
                ┌─────────▼──────────┐              ┌────────────▼─────────────┐
                │ shared/pipeline.py │              │ manufacturing/agents.py  │
                │ 5-stage pipeline   │              │ 4-agent chain (ADK)      │
                └─────────┬──────────┘              └────────────┬─────────────┘
                          └──────────────────┬───────────────────┘
                                             │ same functions
   1 Ingest        2 Score                   3 Explain                 4 Decide        5 Store
 ┌───────────┐  ┌───────────────────┐  ┌─────────────────────┐  ┌──────────────┐  ┌───────────────┐
 │ 28 sample │─▶│ per-asset model   │─▶│ RAG: manual sections │─▶│ risk → action │─▶│ Firestore     │
 │ machines, │  │ + sensor bands    │  │ → Gemini diagnosis   │  │ + work order  │  │ decisions &   │
 │ replay    │  │ + risk fusion     │  │ (fallback if down)   │  │ (idempotent)  │  │ work_orders   │
 └───────────┘  └───────────────────┘  └─────────────────────┘  └──────────────┘  └───────────────┘
   datasets/        models/                  knowledge/                                  Cloud logs
   samples          *.joblib                 maintenance_manual.txt                      + /health stats
```

**Agent chain:** `Sensor Monitor -> Prediction -> Diagnosis (Gemini + RAG) -> Work Order`. The plain Python functions are the source of truth; ADK is a thin orchestration layer around them, so a framework change cannot take the demo down.

### Key design decisions

- **Hybrid, not LLM-only.** The prediction and the risk level come from a trained model plus explicit sensor rules. Gemini only explains the result; it never decides the risk.
- **Grounded answers.** Every diagnosis is built from retrieved manual sections, and the UI shows which ones, which limits hallucination.
- **Never fails in front of the user.** Gemini errors fall back to a local explanation, Firestore errors fall back to memory, and a missing model is flagged as `degraded` instead of crashing.
- **Honest data labels.** Each model records whether it was trained on real, simulated or synthetic data, and the UI displays it.
- **Idempotent work orders.** The same machine, risk and day always produce the same work order id, so a repeated click does not create duplicates.

---

## What it does

1. **Predict.** A trained model per asset gives a failure probability (and remaining useful life for engines).
2. **Check the sensors.** Sensor bands learned from healthy data raise reason codes (for example `HIGH_TORQUE`).
3. **Fuse the two.** An explicit rule combines ML risk and sensor risk into LOW / MEDIUM / HIGH.
4. **Explain.** Retrieval picks the matching sections of the maintenance manual; Gemini writes the diagnosis and cites them.
5. **Act.** A work order is created (idempotent id) and saved to Firestore.

If Gemini is slow or unavailable, the app falls back to a local explanation (shown as `LOCAL_FALLBACK`), so the UI never shows a server error.

### Risk fusion rule

| ML risk | Sensor risk | Overall |
|---|---|---|
| HIGH | any | HIGH |
| MEDIUM | MEDIUM or HIGH | HIGH |
| MEDIUM | LOW | MEDIUM |
| LOW | HIGH | MEDIUM (investigate, do not alarm) |
| LOW | LOW or MEDIUM | LOW |

The ML HIGH threshold is chosen on a validation split. MEDIUM is half of it.

### Agent chain

`Sensor Monitor -> Prediction -> Diagnosis (Gemini + RAG) -> Work Order`

Runs in plain Python or through Google ADK (same decisions). The plain functions are the source of truth; ADK is a thin orchestration layer around them.

---

## Datasets

| Asset | Dataset | Nature | Where it lives |
|---|---|---|---|
| `machine_tool` | AI4I 2020 Predictive Maintenance (UCI) | Synthetic, published benchmark | `manufacturing/data/machine_data.csv` |
| `metro_compressor` | MetroPT-3 (UCI, Porto metro air compressor) | Real sensor data (20,000-row sample) | `manufacturing/data/samples/metropt_sample.csv` |
| `turbofan_engine` | NASA C-MAPSS FD001 | Simulation (run-to-failure, with RUL) | `manufacturing/data/samples/train_FD001.txt` |
| `bearing` | CWRU Bearing Data Center | Real lab recordings with seeded faults | `manufacturing/data/samples/cwru_sample.npz` |

Each trained model records its `data_source` (`real`, `real_simulation`, `synthetic_published`, or `synthetic_standin` if a download failed) in `manufacturing/models/<asset>_metrics.json`. The UI shows it as a badge and `/health` reports it.

---

## Project structure

```
cosmic-voyagers-21-octo-fiesta/
├── main.py                    FastAPI entrypoint (Cloud Run); serves the UI and the API
├── Dockerfile                 Python 3.12; trains the models at image build
├── requirements.txt
├── deploy.ps1                 one-command Cloud Run deploy (Windows PowerShell)
├── env.yaml                   Cloud Run env vars (NOT committed; holds the API key)
├── .env                       local env vars (NOT committed)
├── .gitignore / .dockerignore
├── public/                    frontend served by main.py
│   ├── index.html             dashboard, voice input, agent-chain and replay controls
│   ├── app.js
│   └── styles.css
├── shared/                    domain-agnostic pipeline stages
│   ├── pipeline.py            ingest -> score -> explain -> decide -> store
│   ├── gemini_reasoning.py    stage 3; delegates manufacturing to manufacturing/gemini_reasoning.py
│   ├── agent_decision.py      stage 4: decision from risk
│   └── state_store.py         stage 5: Firestore (in-memory fallback)
└── manufacturing/             the Manufacturing track
    ├── config.py              environment config and JSON logging
    ├── datasets.py            asset registry and dataset loaders
    ├── fetch_datasets.py      downloads MetroPT-3 and CWRU, writes the samples
    ├── download_dataset.py    downloads AI4I
    ├── preprocessing.py       validation and feature building
    ├── risk_rules.py          reason codes, sensor bands, risk fusion
    ├── train.py               trains every asset (grouped split, validation threshold)
    ├── model_scoring.py       score(domain, record) used by the shared pipeline
    ├── rag_retriever.py       section-based manual retrieval
    ├── knowledge/maintenance_manual.txt
    ├── gemini_reasoning.py    Gemini client: timeout, retry, circuit breaker, fallback
    ├── agents.py              four-agent chain (plain Python and Google ADK)
    ├── data_ingestion.py      28 sample machines and the replay stream
    ├── cloud_store.py         Firestore work orders (optional BigQuery rows)
    ├── predict.py, batch_predict.py, threshold_analysis.py
    ├── ingest_to_bigquery.py, bigquery_schema.sql   optional, not required for the demo
    ├── requirements-local.txt pytest and the manufacturing packages
    ├── data/                  AI4I CSV and the dataset samples
    ├── models/                trained .joblib and .json files (generated, not committed)
    └── tests/test_manufacturing.py
```

---

## Run it locally

Use Python 3.12. Commands are for Windows PowerShell; on Mac/Linux use `export NAME=value`.

### 1. Install

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
pip install pytest
```

### 2. Get the data

```powershell
python manufacturing/download_dataset.py            # AI4I
python -m manufacturing.fetch_datasets              # MetroPT-3 and CWRU (slow, needs internet)
```

If you already downloaded MetroPT-3 yourself:

```powershell
python -m manufacturing.fetch_datasets --metropt-csv path\to\MetroPT3.csv
```

The NASA C-MAPSS FD001 file is already in the repo.

### 3. Train

```powershell
python -m manufacturing.train
```

Check that each `manufacturing/models/*_metrics.json` shows `data_source` as `real` (or `real_simulation` for the turbofan). To retrain one asset: `python -m manufacturing.train --asset machine_tool`.

### 4. Test

```powershell
pytest manufacturing/tests -q        # 34 tests
```

### 5. Configure Gemini

Create an API key at <https://aistudio.google.com/apikey>, then create a `.env` file in the repo root:

```
GOOGLE_API_KEY=your_key_here
GOOGLE_CLOUD_PROJECT=your-project-id
GEMINI_MODEL_NAME=gemini-3.1-flash-lite
```

No quotes, no spaces around `=`. Check the model works:

```powershell
python -m manufacturing.gemini_reasoning
```

Success ends with `Reasoning source: GEMINI`. If it says `LOCAL_FALLBACK`, the log line gives the reason:

| Reason | Meaning |
|---|---|
| `call_failed` with 503 or 504 | The model is overloaded. Retry, or switch `GEMINI_MODEL_NAME` to a less busy model. |
| `call_failed` with 404 | Model name not found. List valid names with `python -c "from google import genai; c=genai.Client(); [print(m.name) for m in c.models.list()]"` and drop the `models/` prefix. |
| `no_credentials` | The key is not set in `.env` or the terminal. |
| `sdk_missing` | Run `pip install -r requirements.txt` again. |

### 6. Start the app

```powershell
python main.py
```

Open <http://localhost:8080>. Click TF-001 (expect HIGH risk and a manual-grounded diagnosis), then try **Run 4-agent chain** (Plain and Google ADK) and **Replay sensor stream**. Open `/health` and confirm all four models report `model_loaded: true`.

Without Google Cloud credentials the app still runs: work orders are kept in memory and the UI says "not saved (Firestore not configured)".

---

## Google Cloud setup

### 1. Install the Google Cloud CLI

Download the installer from <https://cloud.google.com/sdk/docs/install> (Windows) or run `brew install --cask google-cloud-sdk` (Mac). Close and reopen your terminal (and VS Code), then check:

```powershell
gcloud --version
```

On Windows PowerShell, `gcloud` may be blocked by the script execution policy. Either use `gcloud.cmd` and `bq.cmd` instead, or run once:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

The commands below use `gcloud.cmd` so they work either way.

### 2. Log in and pick the project

Find your **Project ID** (not the name) in the console project picker, or with `gcloud.cmd projects list`.

```powershell
gcloud.cmd auth login
gcloud.cmd config set project YOUR_PROJECT_ID
gcloud.cmd auth application-default login
```

The project must have billing linked. Create a budget alert under Billing > Budgets & alerts (alerts only; they do not stop spending).

### 3. Enable the services

```powershell
gcloud.cmd services enable firestore.googleapis.com run.googleapis.com aiplatform.googleapis.com artifactregistry.googleapis.com cloudbuild.googleapis.com
```

### 4. Create the Firestore database (once)

```powershell
gcloud.cmd firestore databases create --location=us-central1
```

Run the app locally with `GOOGLE_CLOUD_PROJECT` set in `.env`. Scoring a machine should now save a decision and a work order. Check the Firestore console for the `decisions` and `work_orders` collections.

### 5. Grant permissions to the default compute service account

Newer projects need this before a source deploy works. Replace the project ID and number with yours (the number appears in the 403 error, or on the console dashboard).

```powershell
$P  = "YOUR_PROJECT_ID"
$SA = "serviceAccount:YOUR_PROJECT_NUMBER-compute@developer.gserviceaccount.com"

gcloud.cmd projects add-iam-policy-binding $P --member=$SA --role=roles/storage.objectViewer
gcloud.cmd projects add-iam-policy-binding $P --member=$SA --role=roles/cloudbuild.builds.builder
gcloud.cmd projects add-iam-policy-binding $P --member=$SA --role=roles/artifactregistry.writer
gcloud.cmd projects add-iam-policy-binding $P --member=$SA --role=roles/logging.logWriter
gcloud.cmd projects add-iam-policy-binding $P --member=$SA --role=roles/datastore.user
gcloud.cmd projects add-iam-policy-binding $P --member=$SA --role=roles/aiplatform.user
```

Wait about a minute for the permissions to take effect.

---

## Deploy to Cloud Run

Run everything from the repo root. `--source .` uploads the current folder and builds the `Dockerfile`, which trains the models during the build. Make sure `manufacturing/data/samples/metropt_sample.csv` and `cwru_sample.npz` exist locally first, otherwise the build trains on stand-ins.

### 1. Create `env.yaml` (do not commit it)

```yaml
GOOGLE_CLOUD_PROJECT: "YOUR_PROJECT_ID"
GEMINI_MODEL_NAME: "gemini-3.1-flash-lite"
GOOGLE_API_KEY: "your_key"
```

Add `env.yaml` to both `.gitignore` and `.dockerignore`.

### 2. Create `deploy.ps1`

```powershell
gcloud.cmd run deploy predictive-maintenance-copilot `
  --source . `
  --region us-central1 `
  --allow-unauthenticated `
  --max-instances 3 `
  --timeout 60 `
  --env-vars-file env.yaml `
  --project YOUR_PROJECT_ID
```

The word after `deploy` is the Cloud Run **service name** (lowercase letters, numbers, hyphens). It is not the folder name. Reusing the same name updates the same service and keeps the same URL.

### 3. Run it

```powershell
.\deploy.ps1
```

If PowerShell blocks scripts: `powershell -ExecutionPolicy Bypass -File .\deploy.ps1`. Answer `Y` when asked to enable APIs or create the Artifact Registry repository. The build takes several minutes and prints the **Service URL**.

### 4. Verify the live site

1. Open `<Service URL>/health`: all four models should show `model_loaded: true`.
2. Click TF-001 and M001: the Gemini badge should say "EXPLAINED BY GEMINI", with no "DEGRADED" badge.
3. The work order should say saved; check the Firestore console.
4. Try **Run 4-agent chain** and **Replay sensor stream**.

### 5. Later redeploys

Settings are remembered, so after code changes you can run `.\deploy.ps1` again, or just:

```powershell
gcloud.cmd run deploy predictive-maintenance-copilot --source . --region us-central1
```

### 6. Cost and cold starts

- `--max-instances 3` and a per-IP rate limit (`RATE_LIMIT_PER_MIN`, default 30) cap usage.
- The first request after idle time is slow (cold start). Before recording the demo or judging, keep one instance warm, then set it back to 0 afterwards:

```powershell
gcloud.cmd run services update predictive-maintenance-copilot --min-instances 1 --region us-central1 --project YOUR_PROJECT_ID
gcloud.cmd run services update predictive-maintenance-copilot --min-instances 0 --region us-central1 --project YOUR_PROJECT_ID
```

### Using Vertex AI instead of an API key

On Cloud Run you can drop the API key: set `GOOGLE_GENAI_USE_VERTEXAI=true`, `GOOGLE_CLOUD_PROJECT`, `GOOGLE_CLOUD_LOCATION=us-central1` and `GEMINI_MODEL_NAME` in `env.yaml`, and make sure the service account has `roles/aiplatform.user` (granted above). Check that your chosen model is available in that region.

---

## API

| Endpoint | Purpose |
|---|---|
| `GET /` | Dashboard |
| `GET /health` | Status, per-asset model status, Gemini call and fallback counts |
| `GET /api/records?domain=manufacturing` | The 28 sample machines |
| `POST /api/score` | `{"domain":"manufacturing","record":{"id":"TF-001"}}` runs the full pipeline |
| `GET /api/manufacturing/stream?asset=turbofan_engine` | Scored sensor readings for the replay chart |
| `POST /api/agents/run` | `{"record":{"id":"TF-001"},"mode":"plain"|"adk"}` runs the four-agent chain |
| `GET /api/decisions` | Decision history |

---

## Observability

- One structured JSON log line per Gemini call: `reasoning_source`, latency, model, fallback reason.
- `/health` exposes Gemini call counts and the fallback rate.
- On Cloud Run, open the service's **Logs** tab (or Logs Explorer) to follow these live.

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| `LOCAL_FALLBACK` badge | See the Gemini table above. |
| `/health` shows `model_loaded: false` for an asset | The model file is missing or was saved with another scikit-learn version. Delete `manufacturing/models/<asset>_model.joblib` and run `python -m manufacturing.train --asset <asset>`, then restart the app. |
| "DEGRADED - heuristic fallback" badge | Same cause: no loadable model for that asset. |
| Deploy fails with `403 ... storage.objects.get` | Grant the service account roles (Google Cloud setup, step 5), wait a minute, redeploy. |
| Work order says "not saved (Firestore not configured)" | Set `GOOGLE_CLOUD_PROJECT`, run `gcloud auth application-default login`, create the Firestore database. |
| `gcloud` not recognised in PowerShell | Use `gcloud.cmd`, or set the execution policy as shown above. |
| Ran a command in the wrong folder | Run commands from the repo root, not inside `.git` or the parent folder. |

---

## Honest limits

- AI4I is a synthetic benchmark. The CWRU split comes from only 5 recordings, so its scores are optimistic. C-MAPSS is a simulation, not field data.
- `notify_technician()` writes a log entry only. It does not send messages.
- BigQuery loading (`ingest_to_bigquery.py`) is optional and not verified against a live project.
- Predictions are decision support for qualified maintenance staff, not proof of failure.
- The Google ADK `SequentialAgent` is marked deprecated in ADK 2.x in favour of `Workflow`; it works, and `agents.py` is the only file to change if you migrate.

---

## Status and remaining steps

**Done**

- [x] Four assets trained on their datasets; `/health` shows all models loaded
- [x] Hybrid risk fusion, RAG grounding, Gemini diagnosis with fallback
- [x] Four-agent chain in plain Python and Google ADK
- [x] Dashboard with voice, agent chain and sensor replay
- [x] Firestore state saving verified locally
- [x] Deployed to Cloud Run

**Before submission**

- [ ] Redeploy after the final code changes (`.\deploy.ps1`) and re-run the live-site checks
- [ ] Push the code to the public GitHub repository and fill in the links at the top of this README
- [ ] Confirm the deadline and the category value with the organizers (support+aibuildercup@hack2skill.com)
- [ ] Set `--min-instances 1` shortly before recording and judging, then back to 0 afterwards
- [ ] Record the demo video (under 3 minutes) from the live URL and upload it to YouTube, Vimeo or a public Drive link
- [ ] Prepare the PDF deck: vision, problem, community benefit, feasibility, scalability
- [ ] Submit the four deliverables: deployed link, demo video, public repo, deck

**Optional if time allows**

- [ ] Add a BigQuery load of the sensor history (`ingest_to_bigquery.py`) and verify it on a live project
- [ ] Switch Gemini to Vertex AI and remove the API key from the deployment

---

## Future scope

- **Live streaming:** Pub/Sub and Dataflow ingestion instead of replayed samples.
- **Alerts:** real technician notifications (Pub/Sub, email, chat) from `notify_technician()`.
- **Data platform:** BigQuery for historical readings and Cloud Storage for model artifacts, with a model registry and scheduled retraining.
- **Drift monitoring:** track input and score drift per asset, with alerts when a model degrades.
- **Dashboards:** Cloud Monitoring dashboards and alerting on the fallback rate and latency.
- **More assets and richer manuals:** onboard more equipment types and let each customer upload its own manuals for RAG.
- **Maintenance-system integration:** push work orders to a CMMS (SAP PM, Maximo).
- **Security:** replace the API key with Vertex AI and Secret Manager, add authentication in front of the dashboard.
- **CI/CD:** automated tests and deploy on every push.

---

## Team

Cosmic Voyagers. Built for the Google Cloud AI Builder Cup 2026.