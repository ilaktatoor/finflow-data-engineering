# 0001 — PostgreSQL warehouse, DuckDB lightweight warehouse, one SQL dialect

Status: Accepted

## Context
The project must run a dimensional warehouse locally, without cloud services,
and must also run its core pipeline on a laptop without Docker. Learners
should be able to read one set of SQL files.

## Decision
- **PostgreSQL 17** is the warehouse in the data and full profiles.
- **DuckDB** (embedded, a single file) is the warehouse in the lightweight profile.
- Warehouse, staging and mart SQL is written once, in the subset both engines
  support. Engine-specific statements go into sibling files
  (`01_schema.postgres.sql`, `16_materialized_view.postgres.sql`) that
  `run_sql_file` executes after the shared file.
- DuckDB connections run `SET integer_division = true` so integer `/` truncates
  like PostgreSQL.

## Alternatives
- *PostgreSQL only*: forces Docker for the simplest demo.
- *DuckDB only*: hides transactional-database concepts (MVCC, partial indexes,
  materialized views, EXPLAIN ANALYZE output learners will meet at work).
- *SQLAlchemy Core / an ORM for portability*: hides the SQL the project is
  meant to teach.
- *Separate SQL per engine*: doubles maintenance and invites drift.

## Consequences
- Both engines run the same load, ELT and mart SQL; the services test runs the
  full pipeline on PostgreSQL to prove it.
- Some features are avoided in shared SQL: `TRY_CAST`, `QUALIFY`,
  `CREATE OR REPLACE TABLE`, writable CTEs, partial indexes (DuckDB lacks some,
  PostgreSQL others).
- DuckDB cannot enforce "one current version per customer" with a partial
  unique index; the SCD2 SQL and a test guarantee it instead.

## Trade-offs
PostgreSQL is a row store: analytical scans are slower than a columnar engine,
irrelevant at this size and explicitly called out in
[performance.md](../performance.md). The comparison with DuckDB is itself
teaching material.
