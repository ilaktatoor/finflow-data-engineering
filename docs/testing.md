# Testing

```bash
make test               # unit + contract + lightweight integration (no Docker)
make coverage           # same, with a coverage report
make test-services      # data profile against Docker services (opt-in)
```

## Layout

| Suite | Path | Needs | What it proves |
|---|---|---|---|
| Unit | `tests/unit/` | nothing | money parsing/rounding, generator determinism and exact error counts, every rejection reason, risk rules, Bronze write-once and tamper detection, config, quality gate, API pagination and retry policy |
| Contract | `tests/contracts/` | nothing | generated sources match the published contracts; Silver column names and dtypes are fixed; money is never float |
| Integration (lightweight) | `tests/integration/test_lightweight_pipeline.py`, `test_cli.py` | local disk | the full pipeline on DuckDB + local lake: counts match the generator's report, reconciliation, SCD2 consistency, point-in-time keys, corrections, late data, watermarks, ETL = ELT, marts, idempotent re-runs, failure rollback and recovery, quality gate, replay after the source disappears, the reconciliation guard, and the CLI commands |
| Services | `tests/integration/test_data_services.py` | `make up-data` | the same pipeline on PostgreSQL + MinIO + API: source routing, watermark extraction of only the changed rows, idempotency, ETL = ELT on PostgreSQL, PostgreSQL-only SQL examples, DuckDB reading the lake from MinIO |

Markers: `integration`, `services`. `make test` runs `-m "not services"`;
service tests also skip themselves unless `FINFLOW_TEST_SERVICES=1`.

## How the services tests stay isolated

They create a throwaway warehouse database, operational database and MinIO
bucket (random suffix), run the FastAPI app in-process on a free port against
a temporary landing directory, and drop everything afterwards. Data created
by `make demo-data` is never touched. Only the container API's `/health` is
called directly.

## Deterministic fixtures

All data comes from the seeded generator; the generator writes the expected
numbers (`_generation_report.json`), and tests assert *those* rather than
hard-coded counts. Change the seed or error rate and the tests still hold.

## Results

Last local run (2026-11-24, see `.local/VERIFICATION_REPORT.md` for the log):
**102 passed, 2 deselected** (the service tests) in ~37–49 s; line+branch
coverage **91%**.

Service tests (`make up-data && make test-services`, 2026-11-24): **2 passed**
in ~30 s against PostgreSQL 17.12, MinIO and the FastAPI container. Running them
for the first time found three bugs that no local test could (a masked password
in a rendered URL, PyArrow refusing to create buckets, and a portability gap in
`ROUND`) — the reason service tests exist.

## What is not tested

- Airflow DAGs are not executed by the test suite (they only call CLI commands
  that are). They were verified manually: no import errors, a successful
  incremental run, and a rehearsed failure + recovery (see implementation-status.md).
- `scripts/metabase_setup.py` has no automated test; it was verified manually
  (8 questions, all returning rows).
- Notebooks are not executed in CI.
