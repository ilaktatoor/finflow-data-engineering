# Changelog

All notable changes are documented here. Format based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added
- Deterministic synthetic data generator (small/medium/large, ≤ 10,000 transactions) with intentional, counted data quality issues, late-arriving records and status corrections.
- Lightweight profile: local lake + DuckDB warehouse, no Docker required.
- Bronze layer: write-once raw storage with manifests, SHA-256 checksums and replay.
- Silver layer: Pandas + Pandera validation, quarantine with original payloads, Parquet output partitioned by date, simulated risk rules.
- Quality gate with configurable thresholds; quality facts and reports.
- Star schema with SCD Type 1 dimensions, SCD Type 2 `dim_customer`, point-in-time fact loading, transactional loads with reconciliation guards.
- Batch tracking, extraction watermarks, idempotent upserts, failure injection, backfill.
- ELT path with incremental SQL and ETL↔ELT reconciliation; nine data marts.
- DuckDB lake analytics, reproducible benchmarks, 18 commented SQL examples.
- Data profile: operational PostgreSQL source, FastAPI source simulator, MinIO lake, PostgreSQL warehouse (Docker Compose).
- Full profile: Airflow 3 DAGs and Metabase dashboard setup script.
- Tests (unit, contract, integration, CLI, services), CI workflow, pre-commit hooks.
- Architecture docs, ADRs, runbooks, data contracts, data dictionary and a 16-module learning path.
