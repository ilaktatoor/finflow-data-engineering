-- Business question: For each merchant category, what share of purchase value
--   comes from PREMIUM customers?
-- Explanation: CTEs name intermediate steps so the query reads top-down:
--   purchases -> per category and segment -> pivot into shares.
-- Expected result: one row per category (8), premium share as a percentage.
-- Performance: CTEs are inlined by both engines here (no materialisation),
--   so they cost nothing extra; they are a readability tool.
WITH purchases AS (
    SELECT m.category, c.segment, f.amount_mxn_minor
    FROM fact_transactions f
    JOIN dim_merchant m ON m.merchant_key = f.merchant_key
    JOIN dim_customer c ON c.customer_key = f.customer_key
    WHERE f.status = 'COMPLETED'
),
by_category AS (
    SELECT
        category,
        SUM(amount_mxn_minor) AS total_minor,
        SUM(CASE WHEN segment = 'PREMIUM' THEN amount_mxn_minor ELSE 0 END) AS premium_minor
    FROM purchases
    GROUP BY category
)
SELECT
    category,
    total_minor / 100 AS total_mxn,
    ROUND(100.0 * premium_minor / total_minor, 2) AS premium_share_pct
FROM by_category
ORDER BY premium_share_pct DESC;
