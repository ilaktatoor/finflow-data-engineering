# 11 · Data lake and Parquet

## Learning objectives
- Organise a lake into Bronze/Silver layers with manifests and partitions.
- Use object storage through a filesystem abstraction.
- Query Parquet directly with DuckDB; understand partition pruning.

## Theory
Bronze (raw, immutable), Silver (cleaned, conformed), Gold (business-level,
here the warehouse). Parquet stores columns with types, statistics and
compression; Hive-style directories (`txn_date=2026-01-15/`) let engines skip
whole partitions. Object stores have no real directories, no atomic rename and
no append — which is why the batch marker is written last.

## Where it is implemented
- `src/finflow/ingestion/bronze.py` — layout, manifests, checksums, write-once, replay.
- `src/finflow/common/storage.py` — `LakeStorage` over `pyarrow.fs` (local or MinIO).
- `orchestration/pipeline.py` → `_write_silver` (partitioning), `_write_quarantine`.
- `src/finflow/analytics/lake.py` — DuckDB views over Parquet (`read_parquet(..., hive_partitioning = true)`).
- `notebooks/01_explore_the_lake.ipynb`, `02_sql_on_duckdb.ipynb`.

## Reproduce
```bash
find data/lake -maxdepth 4 | head -30
uv run finflow analytics
cat data/lake/bronze/_batches/batch_id=b000-historical.json | head -30
```

## Expected results
Bronze paths with `source=…/entity=…/batch_date=…/batch_id=…`; Silver
transactions under `txn_date=…` with one file per batch; DuckDB answers five
questions directly from Parquet.

## Exercises
1. Run `EXPLAIN` on a lake query with and without the `txn_date` filter (notebook 02). Find the pruning in the plan.
2. Add a `channel` partition level under `txn_date`. What happens to file counts, and is it worth it at this size?
3. Break it: edit a byte in a Bronze `data.jsonl` and run `finflow etl --batch <id> --force`. What error do you get?
4. Write a compaction command that merges a date partition's per-batch files into one file, safely.

## Common mistakes
- Partitioning on high-cardinality columns (millions of tiny files).
- Overwriting raw data.
- Treating object storage like a POSIX filesystem (rename, append).

## Interview questions
1. Bronze/Silver/Gold — what goes where?
2. Why Parquet over CSV for analytics?
3. What is partition pruning, and how do you choose a partition key?
4. What problems do table formats (Iceberg, Delta) solve on top of Parquet?

Solutions: [solutions/11.md](solutions/11.md)
