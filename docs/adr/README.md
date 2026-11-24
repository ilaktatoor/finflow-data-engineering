# Architecture Decision Records

Short records of decisions that shaped FinFlow: what was decided, why, and what
it costs. Status values: Accepted, Superseded.

| # | Decision |
|---|---|
| [0001](0001-postgresql-warehouse-duckdb-lightweight.md) | PostgreSQL as the warehouse, DuckDB for the lightweight profile, one shared SQL dialect |
| [0002](0002-minio-object-storage.md) | MinIO (S3 API) for the lake, through `pyarrow.fs` |
| [0003](0003-pandas-batch-transformations.md) | Pandas + Pandera for batch transformations |
| [0004](0004-parquet-analytical-storage.md) | Parquet for Silver and the quarantine |
| [0005](0005-airflow-orchestration.md) | Airflow orchestrates; the CLI owns the logic |
| [0006](0006-incremental-loading-and-idempotency.md) | Incremental loading and idempotency strategy |
| [0007](0007-financial-amount-representation.md) | Integer minor units for money |
| [0008](0008-rejection-and-quarantine.md) | Data rejection and quarantine |
| [0009](0009-dependency-pinning.md) | Python 3.12, exact pins and a lockfile |
| [0010](0010-small-datasets.md) | Deliberately small datasets |
