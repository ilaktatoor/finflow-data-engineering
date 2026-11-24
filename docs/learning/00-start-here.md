# 00 · Start here

This learning path uses FinFlow's real code. Every module points at the files
and functions that implement the concept, gives commands whose output you can
check, and ends with exercises that change or break the implementation on
purpose. Solutions are in [`solutions/`](solutions/) — try first.

## Before you begin

```bash
make setup && make demo && make test
```

If `make demo` ends with "days where ETL and ELT disagree: 0" and `make test`
reports all tests passed, you are ready. Work on a branch: several exercises
deliberately break things.

## Map of the modules

| # | Module | Main files |
|---|---|---|
| 01 | [Python for data engineering](01-python-for-data-engineering.md) | `common/config.py`, `common/logging.py`, `common/errors.py` |
| 02 | [Pandas transformations](02-pandas-transformations.md) | `transformations/silver.py`, `common/money.py`, `transformations/risk.py` |
| 03 | [SQL fundamentals](03-sql-fundamentals.md) | `sql/examples/01–07` |
| 04 | [Advanced SQL](04-advanced-sql.md) | `sql/examples/08–18`, `sql/staging/` |
| 05 | [Data modelling](05-data-modeling.md) | `sql/warehouse/01_schema.sql`, `12_load_customers_scd2.sql` |
| 06 | [ETL pipelines](06-etl-pipelines.md) | `orchestration/pipeline.py` |
| 07 | [ELT pipelines](07-elt-pipelines.md) | `warehouse/elt.py`, `sql/staging/` |
| 08 | [Data quality](08-data-quality.md) | `validation/contracts.py`, `validation/quality.py` |
| 09 | [Incremental processing](09-incremental-processing.md) | `pipeline.load`, `sources/operational.py` |
| 10 | [Airflow orchestration](10-airflow-orchestration.md) | `airflow/dags/` |
| 11 | [Data lake and Parquet](11-data-lake-and-parquet.md) | `ingestion/bronze.py`, `common/storage.py`, `analytics/lake.py` |
| 12 | [Testing data pipelines](12-testing-data-pipelines.md) | `tests/` |
| 13 | [Performance optimisation](13-performance-optimization.md) | `analytics/benchmarks.py` |
| 14 | [Cloud architecture concepts](14-cloud-architecture-concepts.md) | (theory) |
| 15 | [Interview preparation](15-interview-preparation.md) | everything |

## Suggested order

Modules 01–02 and 06 give you the backbone in a weekend. 03–05 are the SQL
and modelling core. 07–09 are what separates a script from a pipeline. 10–13
are platform skills. 14–15 prepare you to talk about it.

## Reading the code: first five files

1. `src/finflow/cli/main.py` → `cmd_demo`: the whole story in one function.
2. `src/finflow/orchestration/pipeline.py` → `run_etl`, `ingest`, `transform`, `load`.
3. `src/finflow/transformations/silver.py` → `transform_entity`.
4. `sql/warehouse/20_load_fact_transactions.sql`.
5. `sql/warehouse/12_load_customers_scd2.sql`.

## Conventions used in the modules

- Commands assume the repository root and the lightweight profile.
- "Expected result" describes what you should see; counts come from the
  default seed (42) and the small profile.
- Interview questions have short model answers in the solutions file.
