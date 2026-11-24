# Failure recovery

## Principles

- Bronze is immutable and complete before anything else runs, so any later
  step can be replayed from it.
- The load is one transaction: it commits fully or not at all, and the
  watermark moves only with it.
- Every step attempt is recorded in `fact_pipeline_execution`, failures included.

## Rehearsal (lightweight, measured)

```bash
make demo-failure
```

Which runs, in a separate data directory:

1. `FINFLOW_FAIL_AT=load finflow etl` → `ERROR: Simulated failure at step 'load'`.
   Result observed: `etl_batch.status = FAILED`, `fact_transactions` = 0 rows,
   `etl_watermark` empty.
2. `finflow etl` → batch `LOADED`, 1,910 transactions, `attempts = 2`, and
   `fact_pipeline_execution` holds both the failed and the successful load.

`FINFLOW_FAIL_AT` accepts `ingest`, `load` (and any step name used with
`maybe_fail`). The integration test `test_failure_rolls_back_and_recovers`
automates this.

## Scenarios

| Symptom | Cause | Recovery |
|---|---|---|
| `QUALITY GATE FAILED` (exit 2), batch `QUALITY_FAILED` | too many invalid records | inspect `finflow quality-report --batch <id>` and `rejected/transactions/batch_id=<id>.parquet`; fix upstream; if the source re-sends the batch under the **same id**, Bronze refuses different bytes (see below) |
| `BronzeConflictError: ... Refusing to overwrite` | a batch id was re-sent with different content | treat as a new batch (new id); or, deliberately, delete that batch's Bronze prefix and marker and re-ingest — this discards the evidence of what was first received |
| `BronzeConflictError: Checksum mismatch` | a Bronze object was modified | restore it from backup/MinIO versioning; never edit Bronze |
| `ReconciliationError` | rows were lost between staging and the fact table (a join to a missing dimension, a broken SQL change) | nothing was committed; fix the SQL or the missing reference, rerun `finflow etl --batch <id>` |
| transactions rejected as `unknown_ref:account_id` that are actually valid | the account arrived later (late dimension) | once the account is loaded, `finflow backfill --start <d1> --end <d2>` (or the `finflow_reprocess` DAG) |
| batch stuck in `INGESTED` / `TRANSFORMED` | process died between steps | `finflow etl --batch <id>` resumes; completed steps are idempotent |
| Airflow task failed after retries | transient service outage (database, MinIO, API) | fix the service, Clear the task in the UI |
| ELT and ETL disagree (`reconciliation_mismatched_days > 0`) | a rule changed in one path only | compare `validation/contracts.py` with `sql/staging/10_*.sql`; rerun `finflow elt` after fixing |

## Resetting everything (lightweight)

```bash
make clean-generated && make demo
```
