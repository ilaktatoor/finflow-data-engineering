# 05 · Data modelling

## Learning objectives
- Design a star schema: choose grains, facts, dimensions and keys.
- Implement SCD Type 1 and Type 2 and point-in-time joins.
- Use constraints to make bad data impossible to load.

## Theory
Kimball's process: pick the business process, declare the **grain** (what one
fact row means), choose dimensions, then the facts (measures). Surrogate keys
decouple the warehouse from source keys and make versioned dimensions
possible. SCD1 overwrites, SCD2 keeps history with validity ranges.

## Why it matters
"Design a schema for X" is a standard interview question; the grain is the
first thing a good interviewer listens for.

## Where it is implemented
- `sql/warehouse/01_schema.sql` — every table, its grain in a comment, keys and constraints.
- `sql/warehouse/12_load_customers_scd2.sql` — SCD2.
- `sql/warehouse/11_load_merchants.sql`, `13_*`, `14_*`, `15_*` — SCD1 with an `updated_at` guard.
- `sql/warehouse/20_load_fact_transactions.sql` — surrogate key lookup, point-in-time join.
- `docs/architecture/data-model.md` — the reasoning.
- `transformations/silver.py` → `_finalize`: `attributes_hash` for change detection.

## How it works
Incremental day 1 changes 3 customers. The SCD2 load closes their current rows
(`valid_to = updated_at`) and inserts new current rows. A transaction on day 1
at 08:00 joins the old version if the change happened at 09:00.

## Reproduce
```bash
uv run python -c "
import duckdb; c = duckdb.connect('data/warehouse/finflow.duckdb', read_only=True)
print(c.sql('''SELECT customer_id, segment, city, valid_from, valid_to, is_current
FROM dim_customer WHERE customer_id IN (SELECT customer_id FROM dim_customer GROUP BY 1 HAVING COUNT(*) > 1)
ORDER BY 1, valid_from''').df())"
uv run pytest tests/integration -q -k "scd2 or point_in_time"
```

## Expected results
6 customers with 2 versions each after `make demo` (3 changes per incremental
day × 2 days, if no customer changed twice); 106 rows in `dim_customer`, 100
current.

## Exercises
1. Make `segment` SCD2 but `email` SCD1: an email change should update all versions in place, not create a version.
2. Add `dim_channel` and replace `fact_transactions.channel` with a key. Update the load SQL and marts.
3. Break it: remove the time conditions from the `dim_customer` join in `20_load_fact_transactions.sql`. Run `make clean-generated && make demo`. Which guard stops the load, and why can't a count-and-sum reconciliation catch this bug?
4. Design (on paper) a `fact_account_daily_balance` snapshot fact. What is its grain? Is it additive?

## Suggested modifications
- Add an "unknown member" row (`customer_key = -1`) and load facts with unknown customers instead of rejecting them. Discuss the trade-off with quarantine.

## Common mistakes
- Undeclared grain → double counting.
- SCD2 with inclusive `valid_to` → a boundary event matches two versions.
- Joining facts to an SCD2 dimension on the natural key.
- Summing semi-additive measures (balances) across time.

## Interview questions
1. What is a grain and why decide it first?
2. SCD1 vs SCD2 vs SCD3 — when each?
3. Why surrogate keys?
4. Star vs snowflake schema?
5. How do you handle a fact whose dimension member has not arrived yet?

Solutions: [solutions/05.md](solutions/05.md)
