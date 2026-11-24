# 01 · Python for data engineering

## Learning objectives
- Structure a pipeline as a package with explicit configuration, typed code and clear error types.
- Use structured logging with correlation identifiers.
- Manage resources (connections, transactions) with context managers.

## Theory
Data pipelines fail in production for boring reasons: a missing variable, a
leaked connection, an exception swallowed in a loop, a log line nobody can tie
to a run. Most of the defence is ordinary software engineering applied with
discipline: configuration that fails loudly, exceptions that mean something,
logs that can be joined on an id, resources whose lifetime is visible in the code.

## Why it matters
In an interview, "how do you know which batch caused this error?" or "what
happens if the database connection drops halfway?" are questions about these
foundations, not about Pandas.

## Where it is implemented

| Concept | File | Look at |
|---|---|---|
| Explicit, layered configuration | `src/finflow/common/config.py` | `load_settings`, `read_env_file`, `_required` |
| Domain exceptions | `src/finflow/common/errors.py` | `QualityGateError`, `BronzeConflictError`, `SimulatedFailure` |
| Structured logging + context | `src/finflow/common/logging.py` | `JsonFormatter`, `log_context` |
| Context managers for resources | `src/finflow/orchestration/pipeline.py`, `src/finflow/warehouse/base.py` | `open_runtime`, `track_step`, `DuckDBWarehouse.transaction` |
| Dependency injection where useful | `src/finflow/sources/api_client.py` | `ApiSource(client=...)` used by tests with `httpx.MockTransport` |
| Exit codes for automation | `src/finflow/cli/main.py` | `main` (0 / 1 / 2) |

## How it works
- `load_settings` merges `config/finflow.toml` (behaviour), `.env` (machine) and
  real environment variables (highest priority). In `data` mode, `_required`
  raises `ConfigurationError` naming the missing variable — no silent defaults
  for credentials.
- `log_context(run_id=..., batch_id=...)` sets `ContextVar`s; `JsonFormatter`
  adds them to every record, including records from deep inside helpers that
  know nothing about batches.
- `track_step` is a context manager that measures a step and writes a row to
  `fact_pipeline_execution` in `finally`, so failures are recorded and then
  re-raised (never swallowed).
- `transaction()` commits on success and rolls back on *any* exception
  (`BaseException`, so even `KeyboardInterrupt` cannot leave half a load).

## Reproduce
```bash
uv run finflow --mode data status            # ConfigurationError if .env is missing values
FINFLOW_LOG_LEVEL=INFO uv run finflow etl --batch b000-historical --force 2>&1 | head -3
grep '"step": "load"' data/logs/finflow.log | tail -2
```

## Expected results
- The first command prints `ERROR: FINFLOW_S3_ENDPOINT is required in 'data' mode...` and exits 1 (if your `.env` lacks it).
- Log lines are JSON with `run_id`, `batch_id`, `step`, `duration_ms`.

## Exercises
1. Add a `FINFLOW_LOG_FORMAT=text` option that switches to a human-readable formatter.
2. Make `track_step` also log the exception type on failure as a separate field.
3. Break it: in `track_step`, replace `raise` with `return`. Run
   `FINFLOW_FAIL_AT=load uv run finflow etl --force --batch b000-historical`.
   What does the batch status say, and why is this dangerous?

## Suggested modifications
- Add a `--dry-run` flag to `finflow etl` that runs ingest and validate only.
- Read thresholds from environment variables to override the TOML in CI.

## Common mistakes
- Default credentials in code "for convenience" — they end up in production.
- `except Exception: log.error(...)` without re-raising: the orchestrator sees success.
- Logging the whole DataFrame or record payloads (size and privacy).
- Opening a connection per row instead of per step.

## Interview questions
1. How do you correlate all log lines of one pipeline run?
2. Why use a context manager for a database transaction instead of calling commit at the end?
3. When is dependency injection worth it in a data pipeline, and when is it ceremony?
4. What should a CLI's exit code communicate to an orchestrator?

Solutions: [solutions/01.md](solutions/01.md)
