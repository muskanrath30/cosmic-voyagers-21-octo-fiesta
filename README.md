# Cosmic Voyagers — BFSI: Voice-First Fraud & Risk Assistant

AI Builder Cup 2026 submission. Combines two BFSI sub-use-cases --
transaction fraud detection and loan default risk -- into one
voice-interactive assistant with a live web UI.

## Repo structure

```
cosmic-voyagers/
├── public/               <- frontend (served by main.py)
│   ├── index.html             voice-interactive UI
│   ├── app.js                 record list, scoring, decision history, voice I/O
│   └── styles.css
├── shared/               <- domain-agnostic pipeline stages (used by any vertical)
│   ├── gemini_reasoning.py   Stage 3: plain-language explanation
│   ├── agent_decision.py     Stage 4: approve/escalate/block (or deny)
│   ├── state_store.py        Stage 5: Firestore (or in-memory fallback)
│   └── pipeline.py           chains all 5 stages together
├── bfsi/                 <- BFSI-specific: fraud + loan risk
│   ├── data_ingestion.py     Stage 1: samples REAL records from paysim.csv /
│   │                         vehicle_loan.csv, loaded into memory once at
│   │                         startup; a fresh mixed sample (fraud + normal,
│   │                         default + non-default) is returned on every
│   │                         /api/records call
│   ├── feature_engineering.py   shared by training AND live scoring
│   ├── model_scoring.py      Stage 2: real trained models (heuristic fallback)
│   ├── models/                 trained .joblib files (gitignored)
│   ├── data/                   raw CSVs -- paysim.csv, vehicle_loan.csv (gitignored)
│   └── scripts/
│       ├── inspect_loan_columns.py   run FIRST on a new loan CSV
│       ├── train_fraud_model.py
│       └── train_loan_model.py
├── manufacturing/        <- teammate's domain (not yet built)
├── main.py               <- Cloud Run entrypoint (FastAPI) -- serves the UI
│                             at "/" and all API routes under "/api/*"
├── Dockerfile
└── requirements.txt
```

**Why this split:** stages 1 (ingestion) and 2 (scoring) are genuinely
domain-specific -- BFSI's fraud/loan models have nothing in common with
manufacturing's sensor/failure models. Stages 3-5 (explanation, decision,
state) are the same code regardless of domain. `shared/pipeline.py`
currently imports from `bfsi/` directly; when manufacturing's
`data_ingestion.py` / `model_scoring.py` exist, the pipeline would route
to whichever vertical a request's domain belongs to.

## Frontend

`public/` holds a full voice-interactive UI (mic input via Web Speech
API, text-to-speech for explanations, a browsable record list, live
score/decision display, and a decision history panel). `main.py` serves
`index.html` at `/` and mounts the rest of `public/` as static assets at
`/static` -- so `index.html`'s own asset links point to `/static/app.js`
and `/static/styles.css`, not root paths.

Every API route the frontend calls is prefixed `/api/` (`/api/records`,
`/api/decisions`, `/api/score`, `/api/health`) so FastAPI can serve the
static mount and the API routes without collision.

## Models

Two real trained XGBoost models, not heuristics:
- **Fraud** (`bfsi/models/fraud_model.joblib`) -- trained on PaySim,
  filtered to TRANSFER/CASH_OUT. PR-AUC 0.998, recall 99.6%.
- **Loan risk** (`bfsi/models/loan_model.joblib`) -- trained on the L&T
  Vehicle Loan Default dataset. PR-AUC 0.31, ROC-AUC 0.63 (this dataset's
  known public ceiling is ~0.65-0.67 AUC).

`bfsi/model_scoring.py` uses the real model when the `.joblib` file is
present, and silently falls back to the original rule-based heuristic
otherwise -- so the pipeline still runs with zero setup (e.g. a fresh
clone without the model files).

## Sample data (the UI's record list)

`bfsi/data_ingestion.py` loads `paysim.csv` and `vehicle_loan.csv` into
memory once, at server startup, and splits each into fraud/normal and
default (`LOAN_DEFAULT`)/non-default pools. Every `/api/records` call
then samples fresh from those in-memory pools -- 2 fraud + 4 normal
transactions, 2 default + 4 non-default loans -- so clicking Refresh in
the UI shows a different, genuinely real set of 12 records each time,
with no disk re-read.

## Retraining

```bash
# 1. Put the raw CSVs here first:
#    bfsi/data/paysim.csv
#    bfsi/data/vehicle_loan.csv

# 2. (loan only) confirm columns match what the script expects:
python bfsi/scripts/inspect_loan_columns.py --input bfsi/data/vehicle_loan.csv

# 3. Train both:
python bfsi/scripts/train_fraud_model.py --input bfsi/data/paysim.csv
python bfsi/scripts/train_loan_model.py --input bfsi/data/vehicle_loan.csv --target LOAN_DEFAULT
```

## Run it locally (no GCP account needed)
```bash
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt

python main.py
# then open http://localhost:8080/
```
Without `GOOGLE_API_KEY` set, Gemini calls fall back to a mock
explanation that still correctly states which model (real or heuristic)
produced the score. Without a Firestore emulator/project, saves fall
back to printing `[MOCK SAVE] ...` + an in-memory list -- the UI still
works end-to-end, decisions just won't persist across a server restart.

## Run it locally with real Gemini calls
```bash
export GOOGLE_API_KEY=your_key_here   # get one free at aistudio.google.com/apikey
python main.py
```

## Testing the pipeline directly (bypasses the UI)
```bash
python -m shared.pipeline
```
Note: this standalone test still runs against `shared/data_ingestion.py`'s
original dummy CSV records, not the real sampled data -- that's a
separate, older code path from the UI's `/api/records`, kept only for
quick plumbing checks.

```bash
curl -X POST http://localhost:8080/api/score \
  -H "Content-Type: application/json" \
  -d '{"domain":"transaction","record":{"id":"TXN-1007"}}'

curl -X POST http://localhost:8080/api/score \
  -H "Content-Type: application/json" \
  -d '{"domain":"loan","record":{"id":"LOAN-2002"}}'
```
Other endpoints: `GET /api/records`, `GET /api/decisions`, `GET /api/health`.

## Run it in Docker (same container Cloud Run will use)
```bash
docker build -t cosmic-voyagers .
docker run -p 8080:8080 cosmic-voyagers
```

## Deploy to Cloud Run
```bash
gcloud run deploy cosmic-voyagers \
  --source . \
  --region asia-south1 \
  --allow-unauthenticated \
  --min-instances=1
```
`--min-instances=1` keeps one container warm permanently, so the dataset
load (millions of PaySim rows) only happens once at deploy time rather
than on every cold start -- important given judging allows no retries.

Note: the trained `.joblib` models are gitignored (large binary files) --
either bake them into the Docker image explicitly, or upload them
somewhere the container can fetch at startup, before deploying.