-- Business question: How much time passes between consecutive transactions of
--   the same account, and what is the next transaction's amount?
-- Explanation: LAG/LEAD read the previous/next row within the partition.
--   Short gaps are the raw material of the simulated VELOCITY rule.
-- Expected result: the 20 shortest gaps; the generator's bursts appear as
--   gaps of 30-150 seconds.
-- Performance: one sort by (account_key, event_ts). The PostgreSQL extras add
--   an index on exactly those columns, which lets the planner skip the sort.
WITH gaps AS (
    SELECT
        f.account_key,
        f.transaction_id,
        f.event_ts,
        LAG(f.event_ts) OVER (PARTITION BY f.account_key ORDER BY f.event_ts) AS previous_ts,
        LEAD(f.amount_mxn_minor) OVER (PARTITION BY f.account_key ORDER BY f.event_ts) AS next_amount_minor
    FROM fact_transactions f
)
SELECT
    a.account_id,
    g.transaction_id,
    g.previous_ts,
    g.event_ts,
    EXTRACT(EPOCH FROM g.event_ts - g.previous_ts) AS seconds_since_previous,
    g.next_amount_minor
FROM gaps g
JOIN dim_account a ON a.account_key = g.account_key
WHERE g.previous_ts IS NOT NULL
ORDER BY seconds_since_previous, g.transaction_id
LIMIT 20;
