# 07 · ELT pipelines

## Learning objectives
- Load raw data into the warehouse and transform it with SQL.
- Write incremental SQL and reconcile two implementations.
- Explain when ETL or ELT fits.

## Theory
ELT loads first and transforms inside the warehouse, using its compute.
Raw data stays queryable; transformations are SQL (often managed by dbt).
The costs: raw (possibly sensitive) data in the warehouse, and validation
logic expressed in SQL.

## Where it is implemented
- `src/finflow/warehouse/elt.py` → `load_raw`, `transform_sql`, `refresh_marts`, `reconcile`.
- `sql/staging/00_staging_schema.sql` — untyped staging, `elt_*` tables, `elt_watermark`.
- `sql/staging/10_elt_check_new_transactions.sql` — typing, validation, dedup on new rows only.
- `sql/staging/20_elt_merge_transactions.sql` — upsert, reject log, watermark.
- `sql/quality/etl_elt_reconciliation.sql`.
- Comparison: `docs/architecture/elt-design.md`.

## Reproduce
```bash
uv run finflow elt
uv run python -c "
import duckdb; c = duckdb.connect('data/warehouse/finflow.duckdb', read_only=True)
print(c.sql('SELECT rejection_reason, COUNT(*) FROM elt_rejected_transactions GROUP BY 1 ORDER BY 2 DESC').df())"
```

## Expected results
`reconciliation_mismatched_days: 0`; ELT reject reasons mirror the ETL ones,
but with one reason per record (e.g. `unknown_customer` records appear as
`unknown_ref:customer_id` only).

## Exercises
1. Run `finflow elt` twice. Why does the second run process 0 rows? Find the line responsible.
2. Add `channel` validation to only one path (ETL or ELT) and observe the reconciliation report. Then fix it.
3. Implement an ELT model for `loan_payments` (staging + typed table + reconciliation with `fact_loan_payments`).
4. Break it: remove `SET integer_division = true` from `DuckDBWarehouse`. Run the ELT on a fresh data dir. What happens to `amount_mxn_minor` and the reconciliation?

## Common mistakes
- `TRY_CAST` or engine-specific functions in SQL meant to be portable.
- Full re-transformation of all raw data on every run.
- Dedup with `DISTINCT` when copies differ in metadata.

## Interview questions
1. ETL vs ELT: when each?
2. How would you make an SQL transformation incremental?
3. How do you prove two pipelines produce the same numbers?
4. What does dbt add to the approach in `sql/staging/`?

Solutions: [solutions/07.md](solutions/07.md)
