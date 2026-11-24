# 0006 — Incremental loading and idempotency

Status: Accepted

## Context
Batches arrive daily, may be re-sent, may be replayed after fixes, and may
contain late or corrected records. Re-running anything must not duplicate
business records, and a failure must not lose data or skip it.

## Decision
- **Batch tracking** (`etl_batch`) decides *what* to run; `--force` replays.
- **Extraction watermarks** (`etl_watermark`) for database/API sources: read
  the window `(watermark, window_end]`; the watermark becomes `window_end`
  inside the load transaction.
- **Natural-key upserts** with an ordering guard (`batch_id` for facts,
  `updated_at` for SCD1 dimensions, `attributes_hash` for SCD2).
- **Write-once Bronze** so any batch can be replayed without the source.
- **One transaction per load**, with fact reconciliation before commit.

## Alternatives
- *Truncate and reload*: simple and idempotent but loses history (SCD2) and
  does not scale.
- *Append-only facts with deduplication at read time*: cheap writes, every
  query pays.
- *CDC (logical replication / Debezium)*: the production answer for database
  sources; heavy for a local demo.

## Consequences
- Re-running any batch is safe; tests compare counts and sums before and after.
- Late facts land on their event date; corrections win over older state.
- Watermarks never advance past uncommitted data.

## Trade-offs
`updated_at` watermarks miss rows back-dated before the watermark; a look-back
window would be the next step. Out-of-order SCD2 changes are not back-filled.
Both are documented in incremental-processing.md.
