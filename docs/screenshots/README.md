# Screenshots

Images shown in the main README, captured on 2026-11-24 from a real local run
of the full profile. All data is synthetic; all URLs are localhost.

| File | Shows |
|---|---|
| `metabase-dashboard.png` | Metabase "FinFlow overview" dashboard, top half |
| `metabase-dashboard-quality.png` | the same dashboard, bottom half (rejected records by rule, pipeline step durations) |
| `airflow-dags.png` | the three DAGs with their latest runs |
| `airflow-overview.png` | Airflow home: component health, run and task statistics |
| `airflow-daily-run.png` | `finflow_daily_incremental`: two successful runs and the slowest tasks |
| `airflow-failure-recovery.png` | `finflow_reprocess`: the failed run (`fail_at=load`) and the recovery run |
| `minio-buckets.png` | MinIO console: the `finflow-lake` bucket |
| `minio-lake.png` | inside the bucket: `bronze/`, `rejected/`, `reports/`, `silver/` |
| `source-api-health.png` | Swagger: `GET /health` |
| `source-api-merchants-params.png` / `-response.png` | Swagger: `GET /merchants` parameters and paginated response |
| `source-api-exchange-rates-params.png` / `-response.png` | Swagger: `GET /exchange-rates` parameters and paginated response |

To replace one, keep the file name and stay under ~500 KB (the pre-commit
hook rejects larger files). Never use mock-ups.
