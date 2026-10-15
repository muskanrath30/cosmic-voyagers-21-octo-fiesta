-- infra/bigquery_schema.sql
--
-- BigQuery schema for the Predictive-Maintenance platform.
-- Replace `pm_platform` with your dataset id if different.
--
-- Apply with:
--   bq query --use_legacy_sql=false --project_id=YOUR_PROJECT_ID < infra/bigquery_schema.sql
--   (or use infra/setup_gcp.sh, which creates the dataset then runs this file)

-- ======================================================================
-- 1) raw_sensor_readings — append-only time-series of incoming telemetry.
--    Partitioned by day, clustered by device + sensor for cheap scans.
-- ======================================================================
CREATE TABLE IF NOT EXISTS `pm_platform.raw_sensor_readings`
(
  reading_id      STRING    NOT NULL,   -- UUID for the reading
  device_id       STRING    NOT NULL,   -- machine / asset identifier
  sensor_id       STRING    NOT NULL,   -- which sensor produced the value
  sensor_type     STRING,               -- e.g. temperature, vibration, pressure
  value           FLOAT64   NOT NULL,   -- numeric reading
  unit            STRING,               -- e.g. C, mm/s, bar
  recorded_at     TIMESTAMP NOT NULL,   -- device-side timestamp (UTC)
  ingested_at     TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP(),
  metadata        JSON                  -- free-form tags / context
)
PARTITION BY DATE(recorded_at)
CLUSTER BY device_id, sensor_type
OPTIONS (description = "Raw append-only sensor telemetry");


-- ======================================================================
-- 2) predictions — model output per device / window.
--    Partitioned by day, clustered by device + model version.
-- ======================================================================
CREATE TABLE IF NOT EXISTS `pm_platform.predictions`
(
  prediction_id     STRING    NOT NULL,
  device_id         STRING    NOT NULL,
  model_name        STRING,               -- e.g. rul-regressor
  model_version     STRING,               -- semver / registry version
  prediction_type   STRING,               -- e.g. failure_probability, rul_days
  predicted_value   FLOAT64   NOT NULL,
  confidence        FLOAT64,              -- 0..1
  horizon_hours     INT64,                -- forecast horizon
  features          JSON,                 -- snapshot of inputs (optional)
  predicted_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP()
)
PARTITION BY DATE(predicted_at)
CLUSTER BY device_id, model_name
OPTIONS (description = "Model predictions per device / window");


-- ======================================================================
-- 3) decisions — downstream actions taken (human or automated).
--    Partitioned by day, clustered by device + decision type.
-- ======================================================================
CREATE TABLE IF NOT EXISTS `pm_platform.decisions`
(
  decision_id       STRING    NOT NULL,
  device_id         STRING    NOT NULL,
  prediction_id     STRING,               -- FK to predictions.prediction_id
  decision_type     STRING,               -- e.g. schedule_maintenance, ignore, escalate
  severity          STRING,               -- low | medium | high | critical
  rationale         STRING,               -- explanation (often Gemini-generated)
  actor             STRING,               -- user id or 'system'
  decided_at        TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP(),
  action_taken_at   TIMESTAMP,
  status            STRING,               -- open | actioned | closed
  metadata          JSON
)
PARTITION BY DATE(decided_at)
CLUSTER BY device_id, decision_type
OPTIONS (description = "Maintenance decisions derived from predictions");


-- ======================================================================
-- 4) model_metrics — per-evaluation metrics for monitoring / retraining.
--    Partitioned by day, clustered by model name.
-- ======================================================================
CREATE TABLE IF NOT EXISTS `pm_platform.model_metrics`
(
  metric_id         STRING    NOT NULL,
  model_name        STRING    NOT NULL,
  model_version     STRING,
  metric_name       STRING    NOT NULL,   -- e.g. rmse, mae, f1, precision
  metric_value      FLOAT64   NOT NULL,
  evaluation_split  STRING,               -- train | validation | test
  dataset_version   STRING,
  evaluated_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP(),
  metadata          JSON
)
PARTITION BY DATE(evaluated_at)
CLUSTER BY model_name
OPTIONS (description = "Model evaluation metrics over time");
