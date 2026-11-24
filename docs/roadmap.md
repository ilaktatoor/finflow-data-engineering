# Roadmap

Ideas that would deepen the project, roughly by value. None are implemented.

## Correctness
- Out-of-order SCD2 changes: split an existing version when a change arrives older than the current one.
- Watermark look-back window plus deduplication for back-dated source rows.
- Currency minor units driven by `dim_currency.minor_unit` (JPY = 0, KWD = 3).
- Reprocessing quarantined records individually after a late dimension arrives (today: replay the batch).

## Platform
- Pin the MinIO image by digest, or build MinIO from source (ADR 0002).
- Iceberg or Delta tables for Silver: atomic batch replacement, schema evolution, time travel.
- Silver compaction (one file per partition).
- dbt for the ELT models and marts (tests, docs, lineage graph).
- OpenLineage events from the CLI to visualise lineage.
- Dependabot / scheduled `uv lock --upgrade`.

## Observability
- Prometheus metrics endpoint for step durations and reject rates.
- Alerting on quality-gate failures (Airflow callbacks).

## Learning extensions
- A streaming variant of the transactions source (Redpanda/Kafka) for comparison.
- A real GCP deployment exercise (Cloud Storage, BigQuery, Composer) on a
  personal project, following [the cloud mapping](learning/14-cloud-architecture-concepts.md).
