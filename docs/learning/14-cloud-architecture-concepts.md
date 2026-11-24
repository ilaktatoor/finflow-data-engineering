# 14 · Cloud architecture concepts (Google Cloud mapping)

> **Theoretical material.** FinFlow runs only locally. Nothing here has been
> deployed or tested on Google Cloud; no cloud resources, credentials or
> accounts are used by the project.

## Learning objectives
- Map each local component to a managed Google Cloud service, and explain what changes.
- Discuss partitioning, clustering, columnar costs, identities and least privilege.

## Component mapping

| FinFlow (local) | Google Cloud | What actually changes |
|---|---|---|
| MinIO bucket | Cloud Storage | Same object model and immutability concerns; adds IAM per bucket, object versioning, retention locks (a real write-once guarantee instead of FinFlow's code check), lifecycle rules, regional durability. |
| PostgreSQL warehouse (row store) | BigQuery (columnar, serverless) | No indexes, no `ON CONFLICT`: upserts become `MERGE`; primary/foreign keys are informational, not enforced, so the reconciliation checks become *more* important. Storage and compute are billed separately. |
| DuckDB on Parquet | BigQuery external / BigLake tables over GCS | Query files in place; pruning depends on Hive partition layout, as in FinFlow. |
| Airflow (standalone container) | Cloud Composer (managed Airflow) | Same DAG code; managed scheduler, workers, upgrades. The FinFlow venv would become a container image run by `KubernetesPodOperator` or Cloud Run Jobs. |
| `finflow` CLI in a container | Cloud Run Jobs | Run-to-completion containers with retries; one job per step mirrors the CLI design. |
| JSON logs in a rotating file | Cloud Logging | Structured JSON is parsed automatically; `run_id`/`batch_id` become searchable fields; log-based metrics and alerts. |
| `.env` file | Secret Manager | Secrets fetched at runtime by identity, versioned, audited, rotated. |
| Database users and MinIO root keys | Service accounts + IAM | One service account per workload; no keys at all when using workload identity. |
| Pandas batch transforms | Dataflow (Apache Beam) — or BigQuery SQL | Dataflow for distributed, streaming or very large batch; at FinFlow's size a Cloud Run Job with Pandas is cheaper and simpler. |

## Concepts

**BigQuery partitioning.** Tables partitioned by a DATE/TIMESTAMP column
(e.g. `event_ts` daily) let queries filtered on it read only matching
partitions; you pay for bytes scanned, so pruning is cost control. FinFlow's
`txn_date` Silver partitioning is the same idea on files.

**Clustering.** Within partitions, BigQuery sorts storage blocks by up to four
columns (e.g. `account_key, customer_key`) so filters on them skip blocks.
Roughly what `ix_fact_transactions_account_ts` does in PostgreSQL, without
an index structure.

**Columnar storage and query cost.** Selecting 3 of 20 columns reads only
those 3. `SELECT *` is the classic expensive mistake. FinFlow's Parquet
benchmark shows the size side of this (6×).

**Service accounts and least privilege.** The pipeline account writes to the
lake bucket and the warehouse dataset; the dashboard account only reads marts
(like `analytics_reader`); nobody uses owner credentials, unlike FinFlow's
MinIO root keys.

**Managed orchestration and serverless execution.** You trade control for
not operating schedulers and workers. Costs move from fixed (always-on VMs)
to per-use, which favours FinFlow's short, stateless, retryable steps.

## What would *not* transfer directly
- `INSERT … ON CONFLICT` → `MERGE` in BigQuery.
- Sequences for surrogate keys → `GENERATE_UUID()` or hash keys (BigQuery has no sequences).
- Enforced constraints → tests and reconciliation queries.
- DuckDB's `integer_division` setting → BigQuery `/` always returns FLOAT64; use `DIV()`.

## Exercises
1. Rewrite `20_load_fact_transactions.sql` as a BigQuery `MERGE` (on paper).
2. Design IAM roles for: pipeline, Airflow, analyst, dashboard.
3. Estimate bytes scanned by `mart_daily_transactions` if `fact_transactions` had 1 billion rows, with and without partitioning by date.

## Interview questions
1. How would you move this platform to GCP?
2. Partitioning vs clustering in BigQuery?
3. How do you control BigQuery costs?
4. How should a pipeline authenticate to cloud services?

Solutions: [solutions/14.md](solutions/14.md)
