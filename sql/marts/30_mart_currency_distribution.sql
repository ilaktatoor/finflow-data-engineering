-- Distribution of transactions by original currency.
DROP TABLE IF EXISTS mart_currency_distribution;
CREATE TABLE mart_currency_distribution AS
SELECT
    c.currency_code,
    COUNT(*) AS transactions,
    ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 2) AS share_pct,
    CAST(SUM(f.amount_minor) AS BIGINT) AS original_amount_minor,
    CAST(SUM(f.amount_mxn_minor) AS BIGINT) AS amount_mxn_minor
FROM fact_transactions f
JOIN dim_currency c ON c.currency_key = f.currency_key
GROUP BY c.currency_code;
