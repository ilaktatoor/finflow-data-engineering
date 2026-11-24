# Performance

> **Read this first.** Every number below was measured on one laptop on
> 2026-11-24 with a few thousand rows. At this size, fixed overheads (Python
> start-up, file opening, query planning) dominate. These results show the
> *shape* of trade-offs and how to measure them; they do not predict
> behaviour at enterprise scale, and no scalability claim is made.

Machine: x86_64, 16 vCPU, 14 GiB RAM, Linux 7.3 (CachyOS); project on an
external USB SSD (ext4). Python 3.12.16, pandas 3.1.1, DuckDB 2.0.1.
Reproduce with `make benchmark` (writes `data/reports/benchmarks.json`);
each figure is the median of 5 runs (3 for the slowest).

## End to end

| Run | Wall time | Peak RSS | Warehouse rows |
|---|---|---|---|
| `finflow demo` (small + 2 days, ETL ×2 for idempotency, ELT, marts) | 7.0–7.1 s | 504–559 MiB | 2,090 transactions |
| `finflow etl`, medium profile (historical only) | 3.9 s | 488 MiB | 4,775 transactions |
| `finflow etl`, large profile (historical only) | 4.4 s | 522 MiB | 9,550 transactions |
| `make demo-data` (PostgreSQL + MinIO + API; historical + 1 day, ELT) | 29.9 s | 264 MiB (host CLI) | 2,000 transactions |

The data profile is slower mainly because every step talks to PostgreSQL and
MinIO over the network stack and stages rows with `to_sql`; at this size the
round-trips, not the data, dominate.

Docker footprint (full profile, steady state): Airflow 1.1–1.2 GiB, Metabase
0.4–1.3 GiB (high while warming up), MinIO ~0.2 GiB, API ~0.14 GiB, each
PostgreSQL < 0.12 GiB. Images on disk: 7.3 GB.

Most of the peak RSS is imported libraries (pandas, PyArrow, DuckDB,
Pandera); the data itself is a few MB.

Step durations from `mart_pipeline_performance` (demo): ingest avg 16 ms,
transform avg 448 ms, load avg 496 ms (4 runs each).

## Storage

| Artifact | Size |
|---|---|
| Landing (generated sources) | 0.73 MB |
| Lake (Bronze + Silver + rejected + reports) | 1.45 MB |
| DuckDB warehouse file | 26 MB (DuckDB pre-allocates blocks; the data is far smaller) |
| **All generated artifacts** | **28.9 MB** (target: < 150 MB) |
| Source code (src, sql, tests, airflow, config) | 0.68 MB |
| `.venv` (excluded from the target) | 589 MB |

## Comparisons (`finflow benchmark`)

| Comparison | Result | What it teaches |
|---|---|---|
| CSV vs Parquet, size (2,093 rows) | 403,812 B vs 66,891 B (6.0×) | columnar + compression wins on size |
| CSV vs Parquet, read all columns | 4.2 ms vs 7.3 ms | at 2k rows Parquet's metadata/Arrow conversion costs more than it saves; the win is types and size |
| CSV vs Parquet, read 2 columns | 3.0 ms vs 3.5 ms | column pruning cannot pay off on a 400 KB file |
| Currency conversion: `iterrows` + `Decimal` vs vectorised `Int64` | 110 ms vs 1.43 ms (**77×**) | the one result that is large even at small scale: per-row Python overhead |
| Full read vs chunked (250 rows) aggregation | 2.3 ms vs 15.4 ms; peak 285 vs 312 KiB | chunking bounds memory only when the data is large; here it is pure overhead |
| Low-cardinality columns: object vs category | 464,092 B vs 8,773 B (53×) | categoricals are a memory win at any size |
| 200 point lookups, no index vs ART index (DuckDB) | 187 ms vs 161 ms | per-query overhead dominates; a columnar engine scans 2k rows almost as fast as it probes an index |
| Daily aggregate: full rebuild vs incremental upsert of one day | 5.8 ms vs 5.0 ms | incremental pays off when history is large relative to the new day; 32 days is not |

## SQL plans

`sql/examples/17_indexes_and_explain.sql` runs `EXPLAIN ANALYZE` (output via
`finflow sql-examples --verbose`). On PostgreSQL with ~2,000 rows the planner
may keep a sequential scan even with an index: for a table that fits in a few
pages that is the cheaper plan. Seeing that happen is the lesson.

## What would change at scale (unverified, by reasoning only)

- Parquet's read advantage appears once files are large enough for column and
  row-group pruning to skip I/O.
- The in-memory Pandas transform would need chunking by partition, or a
  different engine (DuckDB, Polars, Spark) once a batch approaches available RAM.
- Per-batch Silver files would need compaction.
- PostgreSQL as a warehouse would need partitioning of `fact_transactions`
  and BRIN indexes on time, or a columnar engine.
