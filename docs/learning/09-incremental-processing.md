# 09 · Incremental processing

## Learning objectives
- Use watermarks and batch tracking; keep them consistent with the data.
- Handle late data, corrections and replays idempotently.

## Theory
Incremental loads read only what changed. A watermark records how far a
consumer has read; it must advance only after the data it covers is durably
written. Late-arriving data and corrections must be applied without
duplicating; replays must produce the same result.

## Where it is implemented
- `orchestration/pipeline.py` → `get_watermark`, `ingest` (watermark passed to sources), `load` (watermark advanced in the transaction), `run_pending`, `backfill`.
- `sources/operational.py` → `OperationalSource.extract` (half-open window on `updated_at`).
- `sources/api_client.py` → `ApiSource.extract` (date and timestamp windows, pagination).
- `sql/warehouse/20_load_fact_transactions.sql` → upsert with batch guard.
- `transformations/silver.py` → `is_late_arriving`.
- `docs/architecture/incremental-processing.md`.

## Reproduce
```bash
uv run finflow generate-incremental && uv run finflow etl && uv run finflow status
uv run python -c "
import duckdb; c = duckdb.connect('data/warehouse/finflow.duckdb', read_only=True)
print(c.sql('SELECT batch_id, COUNT(*) n, SUM(is_late_arriving::INT) late FROM fact_transactions GROUP BY 1 ORDER BY 1').df())"
```

## Expected results
Watermarks for transactions, customers, rates and payments move to the new
window end; merchants/accounts stay at the historical window. Each incremental
batch has 5–7 late rows (3–5 late events + 2 corrections).

## Exercises
1. In data mode, seed two incremental days, then run `etl` once. How many customers does each batch extract from PostgreSQL? Why?
2. Implement a 1-hour look-back for `OperationalSource` and deduplicate the overlap. Which test proves it works?
3. Break it: in `load`, advance the watermark *before* `with rt.warehouse.transaction()`. Run the failure drill in data mode. What data is lost on the retry?
4. Re-send an old batch with a changed status for a transaction that a newer batch already corrected. Which rule keeps the newer status?

## Common mistakes
- Watermark = "now" instead of the extracted window end (gaps and overlaps).
- Watermark updated in a separate transaction from the data.
- `>=` on both window ends (double reads) or `>` on both (gaps).

## Interview questions
1. How do you implement incremental extraction from a database without CDC?
2. What problems does an `updated_at` watermark have?
3. How do you handle late-arriving facts and late-arriving dimensions?
4. Full refresh vs incremental: when is full refresh the better choice?

Solutions: [solutions/09.md](solutions/09.md)
