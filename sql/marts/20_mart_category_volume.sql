-- Card purchase volume by merchant category, ranked by completed value.
DROP TABLE IF EXISTS mart_category_volume;
CREATE TABLE mart_category_volume AS
SELECT
    m.category,
    COUNT(*) AS purchases,
    CAST(SUM(CASE WHEN f.status = 'COMPLETED' THEN f.amount_mxn_minor ELSE 0 END) AS BIGINT) AS completed_mxn_minor,
    CAST(SUM(f.amount_mxn_minor) / COUNT(*) AS BIGINT) AS avg_ticket_mxn_minor,
    RANK() OVER (ORDER BY SUM(CASE WHEN f.status = 'COMPLETED' THEN f.amount_mxn_minor ELSE 0 END) DESC)
        AS value_rank
FROM fact_transactions f
JOIN dim_merchant m ON m.merchant_key = f.merchant_key
GROUP BY m.category;
