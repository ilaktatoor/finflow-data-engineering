# 0005 — Airflow orchestrates; the CLI owns the logic

Status: Accepted

## Context
The platform needs scheduling, retries, timeouts, dependencies, logs and
manual reprocessing, but the core pipeline must also run without Airflow.

## Decision
- **Apache Airflow 3** (standalone mode, LocalExecutor) in the full profile.
- DAGs contain no business logic: every task is a `BashOperator` calling one
  `finflow` CLI command (`step ingest|validate|transform|load`, `elt`, …).
- FinFlow is installed into its own virtualenv inside the Airflow image
  (`/opt/airflow/finflow-venv`), so Airflow's dependency constraints and
  FinFlow's pins (pandas 3, SQLAlchemy 2.1) never meet.
- Tasks pass only small references through XCom (the new batch id); data
  moves through MinIO and PostgreSQL.

## Alternatives
- *PythonOperator importing FinFlow*: couples the two dependency sets.
- *Dagster / Prefect*: good asset-oriented tools; the brief names Airflow and
  it remains the most common orchestrator in job postings.
- *cron + CLI*: no retries, no UI, no dependency graph.

## Consequences
- Every task is reproducible from a shell with the same command.
- One Airflow task = one retryable step, possible because steps communicate
  through storage, not memory.
- `validate` runs with `retries=0`: a quality-gate failure (exit 2) is a data
  problem, retrying cannot fix it.

## Trade-offs
Standalone mode bundles scheduler, API server and DAG processor in one
container: fine for a laptop, not for production. BashOperator gives less
structured task output than native operators.
