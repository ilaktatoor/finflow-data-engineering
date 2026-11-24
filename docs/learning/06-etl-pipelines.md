# 06 · ETL pipelines

## Learning objectives
- Structure extract → raw storage → validate → transform → load as independent, idempotent steps.
- Track batches and step metrics; make loads transactional.

## Theory
ETL transforms before loading. Robust pipelines persist the raw input first
(replayability), make each step idempotent (safe to retry), load inside a
transaction (all or nothing), and record what happened (observability).

## Why it matters
This is the job. Interviewers probe: "what happens if it fails halfway?",
"what if it runs twice?", "how do you know it worked?".

## Where it is implemented
`src/finflow/orchestration/pipeline.py`:
- `ingest` → Bronze, short-circuits when the batch marker exists.
- `validate` / `transform` → Silver; gate before writing.
- `load` → one transaction: stage, SQL loads, `_reconcile_facts`, quality rows, watermarks, `maybe_fail("load")`.
- `run_etl`, `run_pending`, `backfill` → batch orchestration and `etl_batch` status.
- `track_step` → `fact_pipeline_execution`.
- CLI: `finflow etl`, `finflow step <name>`.

## Reproduce
```bash
uv run finflow etl --batch b000-historical --force
uv run finflow status
make demo-failure
```

## Expected results
- `status` shows every batch `LOADED`, watermarks per entity, 2,090 transactions after the default demo.
- `demo-failure`: first run fails at load with 0 facts and `FAILED`; second run loads 1,910 and `attempts = 2`.

## Exercises
1. Add `FINFLOW_FAIL_AT=transform` support (call `maybe_fail("transform")` before Silver is written). What state is left behind, and does a rerun recover?
2. Add a step metric: number of late-arriving transactions per batch into `fact_pipeline_execution.records_out` of a new step `enrich`.
3. Break it: move `maybe_fail("load")` *after* the `with rt.warehouse.transaction():` block. Run the failure drill. What is now committed?
4. Replay: delete `data/landing/b001-*` after loading and run `finflow backfill --start 2026-01-31 --end 2026-01-31`. Why does it work?

## Suggested modifications
- Parallelise transform of independent entities (dimensions) with `concurrent.futures`; measure; decide if it is worth it.

## Common mistakes
- Writing to the target while still extracting (no clean retry point).
- Committing per entity: a failure leaves facts without dimensions.
- Advancing state (watermarks, "processed" flags) before the data commits.
- Retrying a data-quality failure automatically.

## Interview questions
1. How do you make a pipeline idempotent?
2. Why keep raw data if you already have clean data?
3. Walk through what happens when the load fails after loading dimensions but before facts.
4. How would you rerun a single day from three weeks ago?

Solutions: [solutions/06.md](solutions/06.md)
