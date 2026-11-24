-- Customer activity ranking. Uses the *current* customer version for display,
-- while facts stay linked to the historical version (SCD2).
DROP TABLE IF EXISTS mart_customer_activity;
CREATE TABLE mart_customer_activity AS
WITH per_customer AS (
    SELECT
        hist.customer_id,
        COUNT(*) AS transactions,
        CAST(SUM(f.amount_mxn_minor) AS BIGINT) AS gross_mxn_minor,
        MAX(f.event_ts) AS last_transaction_at
    FROM fact_transactions f
    JOIN dim_customer hist ON hist.customer_key = f.customer_key
    GROUP BY hist.customer_id
)
SELECT
    p.customer_id,
    cur.first_name || ' ' || cur.last_name AS customer_name,
    cur.segment AS current_segment,
    p.transactions,
    p.gross_mxn_minor,
    p.last_transaction_at,
    DENSE_RANK() OVER (ORDER BY p.transactions DESC) AS activity_rank
FROM per_customer p
JOIN dim_customer cur ON cur.customer_id = p.customer_id AND cur.is_current;
