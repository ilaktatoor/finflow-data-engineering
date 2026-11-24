# 10 · Airflow orchestration

## Learning objectives
- Model a pipeline as a DAG of retryable tasks with dependencies, retries, timeouts and parameters.
- Keep business logic out of DAG files; pass references, not data.

## Theory
Airflow schedules DAG runs, executes tasks, retries them, and records state
and logs. The scheduler parses DAG files constantly, so top-level code must be
cheap. XCom is for small metadata. Idempotent tasks make "Clear and rerun" safe.

## Where it is implemented
- `airflow/dags/finflow_common.py` — `finflow_task`, `DEFAULT_ARGS` (retries, exponential back-off, 10-minute timeout), templated `FINFLOW_FAIL_AT`.
- `airflow/dags/finflow_historical.py` — manual initial load with TaskGroups.
- `airflow/dags/finflow_incremental.py` — `@daily`, batch id via XCom from `generate-incremental --quiet`.
- `airflow/dags/finflow_reprocess.py` — backfill from Bronze by date range.
- `infrastructure/docker/airflow.Dockerfile` — FinFlow in its own virtualenv.
- `docs/adr/0005-airflow-orchestration.md`.

## How it works
Each task is `finflow --mode data <command>`. `validate_data_quality` has
`retries=0`: exit code 2 means bad data, and retrying cannot fix data.
`simulate_new_business_day` also has `retries=0`: running it twice would
create two business days.

## Reproduce
See `docs/runbooks/pipeline-execution.md` (Airflow section): `make up-full`,
unpause, trigger `finflow_historical_ingestion`, then `finflow_daily_incremental`;
trigger with `{"fail_at": "load"}` to see retries and failure, then recover.

## Expected results
Observed on the build machine: a `finflow_daily_incremental` run succeeds with
8/8 tasks (the historical DAG has 7, without the simulation step). Triggering
`finflow_reprocess` with `{"fail_at": "load"}` fails its backfill task on 3
attempts (1 + 2 retries, with exponential back-off), the downstream tasks
become `upstream_failed`, and the warehouse row counts do not change;
re-triggering without the parameter recovers the batch. Every task carries the
Airflow `run_id` into FinFlow (`FINFLOW_RUN_ID`).

## Exercises
1. Add an `on_failure_callback` that writes the failed task id to a file under `data/reports/`.
2. Use dynamic task mapping to run `validate` for every pending batch in parallel.
3. Break it: add `from finflow.orchestration import pipeline; pipeline.resolve_batches(...)` at the top level of a DAG file. Why does the scheduler slow down, and why does the DAG fail to import?
4. Change the incremental DAG so the batch id is derived from the logical date instead of generated. What changes about backfills?

## Common mistakes
- Heavy imports or I/O at DAG parse time.
- Passing DataFrames through XCom.
- Retrying non-idempotent tasks.
- `catchup=True` on a DAG whose "days" are simulated.

## Interview questions
1. What should and should not go in a DAG file?
2. How do tasks share data?
3. How do you rerun one failed task for a past date?
4. Sensors vs scheduling vs datasets/assets — when each?

Solutions: [solutions/10.md](solutions/10.md)
