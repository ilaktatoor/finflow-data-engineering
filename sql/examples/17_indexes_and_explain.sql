-- Business question: How do we find one account's recent transactions quickly,
--   and how do we check what the engine actually does?
-- Explanation: EXPLAIN shows the chosen plan; EXPLAIN ANALYZE runs the query
--   and reports real row counts and timings. Compare the plan before and after
--   creating an index (the runner rolls the index back).
-- Expected result: an execution plan. In PostgreSQL, after the index exists,
--   the plan for a selective predicate switches from Seq Scan to an Index or
--   Bitmap Index Scan (at ~2,000 rows the planner may still prefer a Seq Scan,
--   which is the correct choice for a table this small). DuckDB uses ART indexes
--   for highly selective equality lookups; range scans rely on zone maps instead.
-- Performance: indexes speed selective reads and slow every write; measure
--   before adding one. `finflow benchmark` measures this on the local data.
CREATE INDEX ix_demo_counterparty ON fact_transactions (counterparty_account_id);
EXPLAIN ANALYZE
SELECT transaction_id, event_ts, amount_mxn_minor
FROM fact_transactions
WHERE counterparty_account_id = 'A000001';
