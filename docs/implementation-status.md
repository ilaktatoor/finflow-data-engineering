# Implementation status

Status as of 2026-11-24. **Verified** means it was executed on the build
machine and the result was checked (by an automated test or by inspecting
output). **Implemented, not verified** means the code/configuration exists but
has not been run successfully yet.

## Lightweight profile — verified

| Component | Status | Evidence |
|---|---|---|
| Configuration, logging, CLI | Verified | `tests/unit/test_config.py`, `tests/integration/test_cli.py` |
| Synthetic generator (3 profiles, error injection, incremental days) | Verified | `tests/unit/test_generator.py`; small/medium/large runs measured |
| File sources (CSV, JSON, JSONL) | Verified | integration tests |
| Bronze (write-once, manifests, checksums, replay) | Verified | `test_bronze.py`, `test_replay_from_bronze_after_source_disappears` |
| Silver (Pandas + Pandera), quarantine, risk rules | Verified | `test_silver.py`, `test_risk.py`, contract tests |
| Quality gate, quality facts and reports | Verified | `test_quality.py`, `test_quality_gate_blocks_the_batch`, `make demo-quality-gate` |
| DuckDB star schema, SCD1, SCD2, point-in-time facts | Verified | `test_scd2_versions_are_consistent`, `test_facts_point_to_the_customer_version_valid_at_event_time` |
| Transactional load, reconciliation guards | Verified | `test_reconciliation_guard_catches_lost_rows`, `test_point_in_time_guard_catches_wrong_customer_version` |
| Incremental batches, watermarks, late data, corrections | Verified | `test_status_corrections_and_late_arrivals`, `test_watermarks_advance_to_last_window` |
| Idempotent re-runs | Verified | `test_forced_rerun_is_idempotent`; `finflow demo` step 2 |
| Failure injection and recovery | Verified | `test_failure_rolls_back_and_recovers`; `make demo-failure` |
| Backfill / reprocessing from Bronze | Verified | `test_cli.py::test_individual_steps_and_backfill` |
| ELT (raw staging, incremental SQL), ETL↔ELT reconciliation | Verified | `test_etl_and_elt_reconcile` (0 mismatched days) |
| Data marts | Verified | `test_marts_answer_business_questions` |
| DuckDB on Parquet lake analytics | Verified | `finflow analytics`, CLI test |
| SQL examples (17 DuckDB-compatible files) | Verified (execute) | `finflow sql-examples`; results inspected manually |
| Benchmarks | Verified | `finflow benchmark`; numbers in performance.md |
| FastAPI simulator + HTTP client (pagination, retries, watermark windows) | Verified in-process | `tests/unit/test_api.py` (TestClient, MockTransport) |
| Lint (ruff), format, type check (mypy) | Verified | clean on `src`, `tests`, `airflow`, `scripts` |
| Unit + contract + lightweight integration tests | Verified | 102 passed, coverage 91% |

## Data and full profiles — verified (second session, 2026-11-24)

Run on the same laptop with Docker 29.10 / Compose 5.8 after the Docker daemon
was enabled.

| Component | Status | Evidence |
|---|---|---|
| `docker-compose.yml`, both images | Verified | `make up-full`: all 6 services healthy; app image 771 MB, Airflow image 3.81 GB |
| Operational PostgreSQL source (`seed`, `updated_at` watermark) | Verified | `test_data_services.py`: the incremental day extracts exactly the 3 changed customers |
| FastAPI container + client (pagination, date windows) | Verified | container `/health`; services test extracts 90 rates / 30 merchants, then only the new day |
| PostgreSQL warehouse (shared SQL + `*.postgres.sql`) | Verified | services test; `make demo-data` gives the same counts as DuckDB |
| MinIO lake via `pyarrow.fs.S3FileSystem` | Verified | Bronze/Silver written to MinIO; `finflow --mode data analytics` reads it with DuckDB |
| ETL↔ELT reconciliation on PostgreSQL | Verified | 0 mismatched days |
| `16_materialized_view.postgres.sql` | Verified | executed by the services test |
| Airflow DAGs | Verified | no import errors; `finflow_daily_incremental` run: 8/8 tasks succeeded; `finflow_reprocess` with `fail_at=load`: 3 attempts failed, nothing committed; re-trigger without it: recovered, idempotent |
| Metabase setup script and dashboard | Verified | dashboard with 8 questions, all return rows, connected as `analytics_reader` |
| Data-profile service tests | Verified | `make test-services`: 2 passed |

Bugs found only by running the real services (all fixed): masked password in
the test URL (`str(URL)` hides it), PyArrow refusing to create the MinIO bucket,
a read-only container unable to create its log directory, a bind mount that
went stale when `clean-generated` recreated `data/landing/`, a `chown` to a group
the Airflow image does not have, `ROUND(double, int)` not existing in
PostgreSQL, and batch `attempts` counted per Airflow task instead of per run.

## Still not verified

| Component | Status | How to verify |
|---|---|---|
| GitHub Actions workflow | Not run (no remote yet) | push to GitHub and check the Actions tab |
| pre-commit hooks | Not run (hook revisions v6.0.0 / v8.30.1 exist upstream; nothing is staged yet) | after the first `git add`: `uv run pre-commit run --all-files` |
| Notebooks in a Jupyter kernel | Code cells executed in order outside Jupyter; not in a kernel | `make notebooks`, Run All |

## Not implemented

- Cloud deployment of any kind (out of scope by design; see learning module 14).
- Items in the [roadmap](roadmap.md).
