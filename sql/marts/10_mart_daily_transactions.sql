-- Daily transaction volume, value and failure rate (all amounts in MXN minor units).
-- Answers: daily volume, total processed, failure percentage, activity over time.
DROP TABLE IF EXISTS mart_daily_transactions;
CREATE TABLE mart_daily_transactions AS
SELECT
    d.full_date,
    d.iso_day_of_week,
    COUNT(*) AS transactions,
    CAST(SUM(CASE WHEN f.status = 'COMPLETED' THEN 1 ELSE 0 END) AS BIGINT) AS completed,
    CAST(SUM(CASE WHEN f.status = 'FAILED' THEN 1 ELSE 0 END) AS BIGINT) AS failed,
    ROUND(100.0 * SUM(CASE WHEN f.status = 'FAILED' THEN 1 ELSE 0 END) / COUNT(*), 2) AS failure_pct,
    CAST(SUM(CASE WHEN f.status = 'COMPLETED' THEN f.amount_mxn_minor ELSE 0 END) AS BIGINT) AS completed_mxn_minor,
    CAST(SUM(f.amount_mxn_minor) AS BIGINT) AS gross_mxn_minor,
    CAST(SUM(CASE WHEN f.is_late_arriving THEN 1 ELSE 0 END) AS BIGINT) AS late_arriving
FROM fact_transactions f
JOIN dim_date d ON d.date_key = f.date_key
GROUP BY d.full_date, d.iso_day_of_week;
