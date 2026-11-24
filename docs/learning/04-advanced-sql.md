# 04 · Advanced SQL

## Learning objectives
- Use window functions (`ROW_NUMBER`, `RANK`, `DENSE_RANK`, `LAG`, `LEAD`, running totals, rolling averages).
- Write recursive CTEs, upserts, views, materialized views.
- Deduplicate and process incrementally in SQL; read `EXPLAIN ANALYZE`.

## Theory
A window function computes over a set of rows related to the current row
(`PARTITION BY`, ordered by `ORDER BY`, limited by a frame like
`ROWS BETWEEN 6 PRECEDING AND CURRENT ROW`) without collapsing them. Ranking
functions differ only on ties. A recursive CTE has an anchor member and a
recursive member joined by `UNION ALL`, iterating until the recursive member
returns no rows.

## Why it matters
Deduplication, "latest record per key", sessionisation, running balances and
period-over-period comparisons are daily work, and the most common
"advanced SQL" interview tasks.

## Where it is implemented

| File | Concept |
|---|---|
| `sql/examples/06_recursive_cte.sql` | recursive amortisation schedule in integer cents |
| `sql/examples/08_window_functions.sql` | partition aggregates beside detail rows |
| `sql/examples/09_row_number_rank_dense_rank.sql` | top-N per group, tie behaviour |
| `sql/examples/10_lag_lead.sql` | gaps between consecutive events |
| `sql/examples/11_running_totals_and_rolling_averages.sql` | frames, calendar densification |
| `sql/examples/12_deduplication.sql` | ROW_NUMBER over a business key |
| `sql/examples/13_incremental_processing.sql` | watermark filter |
| `sql/examples/14_upsert.sql` | `INSERT … ON CONFLICT DO UPDATE … WHERE` |
| `sql/examples/15_views.sql`, `16_materialized_view.postgres.sql` | views vs materialized views |
| `sql/examples/17_indexes_and_explain.sql` | indexes, `EXPLAIN ANALYZE` |
| `sql/examples/18_data_reconciliation.sql`, `sql/quality/etl_elt_reconciliation.sql` | reconciliation, `FULL OUTER JOIN`, `IS DISTINCT FROM` |
| `sql/staging/10_elt_check_new_transactions.sql` | production dedup + incremental + validation in one query |

## How it works
`11_*.sql` first builds one row per day by joining `dim_date` to the facts
(densification): a `ROWS` frame counts rows, so a missing day would silently
make "7 rows" span 8 calendar days. Only then does it apply the window over ~30
rows instead of thousands of facts.

`14_upsert.sql` shows the ordering guard: the stale re-send (`b001` after
`b002`) does not overwrite the newer status because of
`WHERE EXCLUDED.batch_id >= demo_upsert.batch_id`.

## Reproduce
```bash
uv run finflow sql-examples --verbose | sed -n '/06_recursive_cte/,/07_conditional/p'
uv run finflow sql-examples --verbose | sed -n '/14_upsert/,/15_views/p'
```

## Expected results
- `06_recursive_cte`: 24 rows for loan L00001 with the default seed; interest decreases; the last `closing_minor` is 0.
- `09_*`: 9 rows (3 per segment).
- `12_deduplication`: the injected duplicates and the status corrections, with `kept_as_latest`.
- `14_upsert`: one row, `COMPLETED`, `b002`.

Examples run inside a transaction that is rolled back (`analytics/sql_examples.py`), so DDL in them changes nothing.

## Exercises
1. Using `LAG`, compute day-over-day change in completed value and the percentage change.
2. Rewrite `09` with `QUALIFY` (DuckDB only). Why can't the shared SQL use it?
3. Write a recursive CTE that lists every day between the first and last transaction without using `dim_date`.
4. Break it: change the frame in `11` to `RANGE BETWEEN 6 PRECEDING AND CURRENT ROW` on a DATE order key. What error or result do you get on each engine?
5. Deduplicate `stg_raw_transactions` keeping the *first* copy instead of the latest; which copies change?

## Suggested modifications
- Turn `mart_daily_transactions` into an incremental model: upsert only days touched by the latest batch.

## Common mistakes
- `ROW_NUMBER` without a deterministic `ORDER BY` (non-reproducible results).
- Filtering a window result in `WHERE` (it is computed after WHERE).
- Using `RANK` when you need exactly N rows.
- Running totals over gaps without densifying first.
- Upserts without an ordering guard: replays overwrite newer data.

## Interview questions
1. Difference between ROW_NUMBER, RANK and DENSE_RANK?
2. How do you get the latest record per customer?
3. ROWS vs RANGE frames?
4. When is a materialized view a better choice than a table you rebuild?
5. How do you read `EXPLAIN ANALYZE` — what do you look at first?

Solutions: [solutions/04.md](solutions/04.md)
