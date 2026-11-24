# 03 · SQL fundamentals

## Learning objectives
- Write joins, aggregations, `GROUP BY … HAVING`, subqueries, CTEs and conditional aggregation against a star schema.
- Read a query plan at a basic level.

## Theory
SQL evaluates logically in this order: `FROM/JOIN → WHERE → GROUP BY → HAVING
→ SELECT → ORDER BY → LIMIT`. That order explains most beginner errors:
`WHERE` cannot filter on an aggregate (use `HAVING`), and a column alias from
`SELECT` is not visible in `WHERE`.

In a star schema, a fact table holds measurements at a fixed grain and joins
to small dimensions on surrogate keys.

## Why it matters
Every data role tests SQL. Business questions in interviews look exactly like
the ones in `sql/examples/`.

## Where it is implemented
Each file has a header with the business question, explanation, expected
result and performance notes:

| File | Concept |
|---|---|
| `sql/examples/01_inner_join.sql` | INNER JOIN, filtering on dimension attributes |
| `sql/examples/02_left_join.sql` | LEFT JOIN as an anti-join (accounts without transactions) |
| `sql/examples/03_group_by_having.sql` | aggregation, HAVING |
| `sql/examples/04_subqueries.sql` | correlated and scalar subqueries |
| `sql/examples/05_cte.sql` | CTEs for readable multi-step logic |
| `sql/examples/07_conditional_aggregation.sql` | `SUM(CASE …)`, `COUNT(*) FILTER (WHERE …)` |
| `sql/marts/10_mart_daily_transactions.sql` | a production aggregation |

## How it works
`02_left_join.sql` keeps every account, then selects those whose fact side is
NULL. Putting `f.status = 'COMPLETED'` in the `WHERE` clause would turn it back
into an inner join (NULL = 'COMPLETED' is not true); putting it in the `ON`
clause would keep the anti-join semantics for "no completed transactions".

## Reproduce
```bash
uv run finflow sql-examples --verbose | sed -n '/01_inner_join/,/02_left_join/p'
uv run python -c "
import duckdb; c = duckdb.connect('data/warehouse/finflow.duckdb', read_only=True)
print(c.sql(open('sql/examples/07_conditional_aggregation.sql').read()).df())"
```

## Expected results
- `01_inner_join`: 20 rows of completed purchases with merchant and category.
- `02_left_join`: 0 rows with the default seed (every account transacted) — a valid result; exercise 1 changes that.
- `07_conditional_aggregation`: 6 channels; failure rates of a few percent.

## Exercises
1. Change `02_left_join.sql` to list accounts with no **completed** transactions. Where must the status condition go?
2. Write a query: per merchant category, number of distinct customers and average ticket in MXN.
3. Rewrite `04_subqueries.sql` with a CTE that pre-computes the per-type average. Compare `EXPLAIN` output.
4. Break it: in `05_cte.sql`, join `dim_customer` on `customer_id` instead of `customer_key`. Why do totals inflate for some categories?

## Suggested modifications
Add `18b`: which day of the week has the highest failure rate (use `dim_date.iso_day_of_week`).

## Common mistakes
- Filtering the right table of a LEFT JOIN in WHERE.
- `COUNT(column)` vs `COUNT(*)` (NULLs are not counted by the former).
- Integer division (`failed / total` = 0 in PostgreSQL). FinFlow multiplies by `100.0`.
- Joining an SCD2 dimension on the natural key (one fact × N versions).

## Interview questions
1. Difference between WHERE and HAVING?
2. Write "customers with more than 30 transactions" two ways.
3. When does a LEFT JOIN behave like an INNER JOIN by accident?
4. What does `COUNT(DISTINCT x)` cost compared with `COUNT(x)`?

Solutions: [solutions/03.md](solutions/03.md)
