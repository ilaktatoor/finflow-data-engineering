-- Business question: Which customers made more than 30 transactions, and how
--   much value did they move?
-- Explanation: GROUP BY aggregates per customer; HAVING filters on the
--   aggregate (WHERE cannot, because it runs before grouping).
-- Expected result: the most active customers, highest count first.
-- Performance: one hash aggregate over the fact table. The join to
--   dim_customer happens after aggregation would be cheaper on large data;
--   here the planner handles it either way.
SELECT
    c.customer_id,
    COUNT(*) AS transactions,
    SUM(f.amount_mxn_minor) / 100 AS gross_mxn,
    MIN(f.event_ts) AS first_seen,
    MAX(f.event_ts) AS last_seen
FROM fact_transactions f
JOIN dim_customer c ON c.customer_key = f.customer_key
GROUP BY c.customer_id
HAVING COUNT(*) > 30
ORDER BY transactions DESC, c.customer_id;
