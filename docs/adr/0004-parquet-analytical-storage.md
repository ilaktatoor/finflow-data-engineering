# 0004 — Parquet for Silver and the quarantine

Status: Accepted

## Context
Silver datasets must keep types exactly (integer cents, nullable booleans,
UTC timestamps), be partitionable, and be readable by Pandas, DuckDB and any
cloud warehouse.

## Decision
Write Silver and the quarantine as **Parquet** (zstd compression) through
PyArrow. Transactions are partitioned Hive-style by `txn_date`; every other
entity by `batch_id`. Bronze keeps the original bytes (CSV/JSON/JSONL) instead,
because Bronze must preserve exactly what was received.

## Alternatives
- *CSV*: loses types (cents become floats, timestamps text), ~6× larger here.
- *Delta Lake / Iceberg*: ACID tables, time travel and schema evolution on the
  lake; valuable at scale, unnecessary ceremony for this size (see roadmap).
- *Avro*: row-oriented, better for streaming writes than analytical reads.

## Consequences
- Measured on the demo data: 2,093 transactions are 66,891 bytes as Parquet vs
  403,812 bytes as CSV (6.0×). Read time at this size is *not* better (see
  performance.md): the gain is types, size and column pruning, not speed.
- Each batch writes its own file into a date partition, so late-arriving data
  never rewrites existing files; reprocessing replaces only that batch's files.
- Many small files is the known cost of per-batch files; compaction is on the roadmap.

## Trade-offs
Plain Parquet has no transactions: a crash between deleting and rewriting a
batch's Silver files leaves the batch incomplete until it is reprocessed.
Bronze replay makes that recoverable, which is why Bronze is immutable.
