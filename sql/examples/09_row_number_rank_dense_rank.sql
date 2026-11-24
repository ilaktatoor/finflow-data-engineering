-- Business question: Who are the top 3 customers by completed value in each
--   segment, and how do ties behave?
-- Explanation: ROW_NUMBER gives a unique sequence (ties broken arbitrarily,
--   here by customer_id); RANK leaves gaps after ties (1,1,3); DENSE_RANK does
--   not (1,1,2). Filtering on a window result needs an outer query (or QUALIFY,
--   which DuckDB supports and PostgreSQL does not).
-- Expected result: up to 3 rows per segment (RETAIL, PREMIUM, SMB) = 9 rows.
-- Performance: one sort per partition; cheap at this size.
WITH per_customer AS (
    SELECT c.segment, c.customer_id, SUM(f.amount_mxn_minor) AS completed_minor
    FROM fact_transactions f
    JOIN dim_customer c ON c.customer_key = f.customer_key
    WHERE f.status = 'COMPLETED'
    GROUP BY c.segment, c.customer_id
),
ranked AS (
    SELECT
        segment,
        customer_id,
        completed_minor,
        ROW_NUMBER() OVER (PARTITION BY segment ORDER BY completed_minor DESC, customer_id) AS row_num,
        RANK() OVER (PARTITION BY segment ORDER BY completed_minor DESC) AS rnk,
        DENSE_RANK() OVER (PARTITION BY segment ORDER BY completed_minor DESC) AS dense_rnk
    FROM per_customer
)
SELECT * FROM ranked WHERE row_num <= 3 ORDER BY segment, row_num;
