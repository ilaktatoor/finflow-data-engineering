# Pipeline execution

All commands accept `--mode lightweight|data` (default from `FINFLOW_MODE`).

## Everyday commands

| Goal | Command |
|---|---|
| Generate the historical batch | `finflow generate [--profile small|medium|large] [--error-rate 0.05] [--force]` |
| Generate the next business day | `finflow generate-incremental [--count N]` |
| Process every pending batch | `finflow etl` |
| Process one batch | `finflow etl --batch b001-2026-01-31` |
| Reprocess an already loaded batch | `finflow etl --batch <id> --force` |
| Run one step | `finflow step ingest|validate|transform|load --batch <id>` |
| SQL path + marts + reconciliation | `finflow elt` |
| Rebuild marts only | `finflow marts` |
| Status, watermarks, row counts | `finflow status` |
| Quality summary | `finflow quality-report [--batch <id>]` |
| Reprocess a date range from Bronze | `finflow backfill --start 2026-01-30 --end 2026-02-01` |
| Lake analytics with DuckDB | `finflow analytics` |
| (data) Write landing batches to the operational DB | `finflow --mode data seed [--batch <id>]` |

Exit codes: `0` success, `1` expected error (message on stderr), `2` quality
gate failed.

## Logs

Structured JSON on stderr and in `data/logs/finflow.log` (rotated at 1 MB, 3
files kept; `[logging]` in `config/finflow.toml`). Every line has `run_id` and
`batch_id`:

```bash
grep '"batch_id": "b001-2026-01-31"' data/logs/finflow.log | jq -c '{ts, msg, step, status, duration_ms}'
```

Step timings are also in the warehouse: `fact_pipeline_execution` and
`mart_pipeline_performance`.

## Airflow

| DAG | Trigger | Does |
|---|---|---|
| `finflow_historical_ingestion` | manual (param `batch_id`) | seed → ingest → validate → transform → load → ELT → quality report |
| `finflow_daily_incremental` | `@daily` or manual | simulate a business day → seed → the same chain |
| `finflow_reprocess` | manual (params `start_date`, `end_date`) | backfill from Bronze → marts → quality report |

- **Trigger**: UI "Trigger DAG" (with config), or
  `docker compose exec airflow airflow dags trigger finflow_historical_ingestion`.
- **Inspect task logs**: UI → DAG run → task → Logs; on disk under
  `airflow/logs/dag_id=.../run_id=.../task_id=.../`.
- **Retry a failed task**: UI → task → Clear (downstream tasks are cleared
  too); or `airflow tasks clear <dag_id> -t <task_regex> -s <date> -e <date>`.
- **Reprocess historical dates**: trigger `finflow_reprocess` with the range.
- **Correlate logs**: every task passes Airflow's `run_id` to FinFlow
  (`FINFLOW_RUN_ID`), so `etl_batch.last_run_id`, `fact_pipeline_execution.run_id`
  and the JSON logs carry the Airflow run id.
- **Simulate a failure**: trigger with `{"fail_at": "load"}`; the load task
  fails after staging, inside its transaction. Verified: `finflow_reprocess`
  with `fail_at=load` failed 3 attempts (1 + 2 retries), downstream tasks were
  `upstream_failed`, the warehouse kept exactly its previous row counts.
- **Recover**: trigger again without `fail_at`. Verified: the batch went back to
  `LOADED` with identical fact counts. For a failed run of the daily DAG, the
  batch it created stays `FAILED` until `finflow_reprocess` (or `finflow etl`)
  processes it — a new daily run creates a *new* day. See [failure-recovery.md](failure-recovery.md).
