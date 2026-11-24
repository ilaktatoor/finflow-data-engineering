# ELT design

The ELT path loads raw transactions **untyped** into the warehouse and does
all typing, validation, deduplication and aggregation in SQL. It runs next to
the ETL path on the same batches, so the two can be reconciled.
Code: `src/finflow/warehouse/elt.py`, SQL: `sql/staging/`, `sql/marts/`.

## Steps

| Step | What happens | SQL |
|---|---|---|
| `load_raw` | Bronze JSONL → `stg_raw_transactions`, every field `VARCHAR`, plus `raw_record`, `batch_id`, `record_position` | insert with `ON CONFLICT (batch_id, record_position) DO NOTHING` |
| `transform_sql` (1) | build `elt_work_checked` from rows **above the ELT watermark** only: trim/upper, regex-validated casts, rule checks, references against the conformed dimensions, `ROW_NUMBER` for duplicates | `10_elt_check_new_transactions.sql` |
| `transform_sql` (2) | upsert valid rows into `elt_transactions`, record rejects/duplicates in `elt_rejected_transactions`, advance `elt_watermark` — one transaction | `20_elt_merge_transactions.sql` |
| marts | rebuild marts, including `mart_elt_daily_summary` | `sql/marts/*.sql` |
| reconcile | compare ETL and ELT per day (count, failures, MXN value) | `sql/quality/etl_elt_reconciliation.sql` |

## Incremental SQL

`stg_raw_transactions.load_seq` comes from a sequence, so it only grows. The
ELT remembers the last `load_seq` it transformed (`elt_watermark`) and reads
only newer rows. Upserting with `WHERE EXCLUDED.load_seq > elt_transactions.load_seq`
keeps re-runs and replays order-safe.

## Portability between DuckDB and PostgreSQL

The ELT SQL runs unchanged on both engines. The care it took:

- **No `TRY_CAST`** (PostgreSQL lacks it): text is validated with an anchored
  regex (`~` behaves the same on both) before casting.
- **Integer division**: `/` on integers truncates in PostgreSQL but returns a
  `DOUBLE` in DuckDB. FinFlow sets `SET integer_division = true` on every DuckDB
  connection (`warehouse/base.py`), so the currency conversion
  `(amount_minor * rate_micros + 500000) / 1000000` is exact on both.
- **No `CREATE OR REPLACE TABLE`**: `DROP TABLE IF EXISTS` + `CREATE TABLE AS`.
- **No writable CTEs** (DuckDB lacks them): the checked rows go to a work table
  that two `INSERT ... SELECT` statements read.

## Differences from the ETL path (on purpose)

| Aspect | ETL | ELT |
|---|---|---|
| Where logic runs | Python (Pandas, Pandera) | SQL in the warehouse |
| Raw data in warehouse | no (Bronze only) | yes (`stg_raw_transactions`) |
| Rejection reasons per record | all of them | the first failing rule |
| Timestamp formats accepted | any ISO-8601 | exactly `YYYY-MM-DDTHH:MM:SSZ` |
| References checked against | Silver (lake) | conformed warehouse dimensions (loaded by the ETL) |
| Entities | all eight | transactions |

Because the accepted sets must be identical, every rule in
`validation/contracts.py` has a twin in `10_elt_check_new_transactions.sql`.
`finflow elt` reports the days where the two paths disagree; the integration
tests require zero.

## When to use which

- **ETL** when validation is complex, needs a general-purpose language, must
  keep sensitive raw data out of the warehouse, or when the warehouse is
  expensive per query.
- **ELT** when the warehouse is the cheapest scalable compute you have
  (BigQuery, Snowflake), when analysts own the transformations in SQL, and when
  keeping raw data in the warehouse for re-modelling is valuable.

Most real platforms mix both, as FinFlow does: ETL for conformance and
quality, ELT for modelling and marts.
