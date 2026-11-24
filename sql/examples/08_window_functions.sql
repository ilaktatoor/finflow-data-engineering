-- Business question: How does each transaction compare with the customer's own
--   average, and what share of the customer's total does it represent?
-- Explanation: window functions compute per-partition aggregates *without*
--   collapsing rows, so detail and context sit side by side. Compare with
--   04_subqueries.sql: same idea, one pass, no self-reference.
-- Expected result: one row per transaction for the 5 most active customers.
-- Performance: requires a sort (or hash partition) by customer_key. An index
--   on (customer_key) does not help a full-table window; it helps selective filters.
WITH ranked_customers AS (
    SELECT customer_key FROM fact_transactions
    GROUP BY customer_key
    ORDER BY COUNT(*) DESC, customer_key
    LIMIT 5
)
SELECT
    c.customer_id,
    f.transaction_id,
    f.amount_mxn_minor,
    AVG(f.amount_mxn_minor) OVER (PARTITION BY f.customer_key) AS customer_avg_minor,
    ROUND(100.0 * f.amount_mxn_minor / SUM(f.amount_mxn_minor) OVER (PARTITION BY f.customer_key), 2)
        AS pct_of_customer_total,
    COUNT(*) OVER (PARTITION BY f.customer_key) AS customer_transactions
FROM fact_transactions f
JOIN ranked_customers r ON r.customer_key = f.customer_key
JOIN dim_customer c ON c.customer_key = f.customer_key
ORDER BY c.customer_id, f.event_ts;
