-- Ornek "knowledge core" tablosu. Kendi projenizde bu tabloyu kendi gercek
-- veri semanizla degistirin; ajan'daki query_live_well_pressure aracini da
-- buna gore guncelleyin.
--
-- Kullanim (Cloud Shell):
--   bq mk --dataset ${PROJECT_ID}:telemetry_data
--   bq query --use_legacy_sql=false < scripts/setup_bigquery.sql
-- (PROJECT_PLACEHOLDER yerine kendi PROJECT_ID'nizi koymayi unutmayin, ya da
--  calistirmadan once `sed -i "s/PROJECT_PLACEHOLDER/${PROJECT_ID}/g"` kullanin.)

CREATE OR REPLACE TABLE `PROJECT_PLACEHOLDER.telemetry_data.well_metrics` (
    well_id STRING,
    pressure_psi INT64,
    temperature_c FLOAT64,
    timestamp TIMESTAMP
);

INSERT INTO `PROJECT_PLACEHOLDER.telemetry_data.well_metrics` VALUES
('WELL-101', 4180, 118.5, CURRENT_TIMESTAMP()),
('WELL-102', 3200, 95.0, CURRENT_TIMESTAMP());
