-- Business question: How can analysts query "current customers with their
--   lifetime activity" without repeating the SCD2 filter every time?
-- Explanation: a view stores the query, not the data. It always reflects the
--   current tables and hides the is_current filter from consumers.
--   (Rolled back by the example runner.)
-- Expected result: 100 rows, one per customer, ordered by activity.
-- Performance: a view is expanded into the calling query at plan time, so it
--   costs exactly as much as the underlying query each time it is read.
--   See 16_materialized_view.postgres.sql for the stored alternative.
CREATE VIEW v_customer_lifetime AS
SELECT
    cur.customer_id,
    cur.segment,
    cur.city,
    COUNT(f.transaction_id) AS lifetime_transactions,
    COALESCE(SUM(f.amount_mxn_minor), 0) AS lifetime_mxn_minor
FROM dim_customer cur
LEFT JOIN dim_customer hist ON hist.customer_id = cur.customer_id
LEFT JOIN fact_transactions f ON f.customer_key = hist.customer_key
WHERE cur.is_current
GROUP BY cur.customer_id, cur.segment, cur.city;
SELECT * FROM v_customer_lifetime ORDER BY lifetime_transactions DESC, customer_id LIMIT 10;
