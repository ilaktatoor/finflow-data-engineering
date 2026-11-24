# Incremental processing, idempotency and late data

## Three mechanisms, three jobs

| Mechanism | Where | Answers |
|---|---|---|
| **Batch tracking** (`etl_batch`) | every profile | "Has this batch been loaded?" — `run_pending` skips `LOADED` batches |
| **Extraction watermarks** (`etl_watermark`) | data profile: PostgreSQL and API sources | "What changed upstream since the last successful load?" |
| **ELT watermark** (`elt_watermark`) | warehouse | "Which raw rows has SQL not transformed yet?" |

## Extraction watermarks

For the operational database the pipeline reads the half-open window
`(watermark, batch.window_end]` on `updated_at`:

```sql
WHERE updated_at > :lower AND updated_at <= :upper
```

(`sources/operational.py`). The API source passes the same window as query
parameters (`sources/api_client.py`). After the batch commits, the watermark
becomes `batch.window_end`, **inside the same transaction as the data**
(`pipeline.load`). If the load fails, the watermark does not move, and the
next run extracts the same window again.

The integration test `test_failure_rolls_back_and_recovers` asserts the
watermark table is empty after a failed load. The services test checks that an
incremental day extracts exactly the 3 changed customers and the 3 new rates
from PostgreSQL and the API.

File sources do not need a watermark (each landing batch is its own file),
but the watermark is still recorded for freshness monitoring.

## Idempotency

Running the same batch twice must not duplicate anything:

- Bronze: identical bytes → no-op; the batch marker short-circuits extraction.
- Silver: the batch's files are replaced.
- Warehouse: upserts on natural keys; SCD2 compares hashes, so an unchanged
  customer gets no new version; `fact_data_quality` rows for the batch are
  replaced; `fact_pipeline_execution` keeps every attempt (that is its purpose).
- ELT: `(batch_id, record_position)` is unique in staging.

`test_forced_rerun_is_idempotent` re-runs every batch with `--force` and
compares counts and sums of facts, customers, quality rows and payments.

## Late-arriving data

**Late facts** (an event from a previous day that arrives today):

- The generator sends 3–5 per incremental day, dated up to 7 days back.
- Silver flags them `is_late_arriving = true` (event before the batch window).
- They are written to the Silver partition of their *event* date, so
  partitions for past days receive new files (one per batch — nothing is rewritten).
- The warehouse upsert places them on their event date; marts are rebuilt in full.

**Corrections** (a known transaction whose state changed): upserted; the batch
guard keeps the newest version.

**Late dimensions** (a transaction referencing an account the lake has not
seen yet): rejected with `unknown_ref:account_id` and kept in quarantine with
its payload. Once the account arrives, `finflow backfill` (or the
`finflow_reprocess` DAG) replays the affected batches from Bronze; reference
checks then see the account.

**Late SCD2 changes** older than the current version are ignored — see the
limitation in [data-model.md](data-model.md).

**Known watermark limitation**: a source row whose `updated_at` is set to a
time *before* the current watermark (clock skew, back-dated writes) is never
extracted. Production systems add a look-back overlap and deduplicate; FinFlow
documents the problem instead of hiding it.
