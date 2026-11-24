-- Business question: What is the cumulative completed value over the period,
--   and the 7-day rolling average of daily value?
-- Explanation: SUM() OVER (ORDER BY day) gives a running total; a frame of
--   ROWS BETWEEN 6 PRECEDING AND CURRENT ROW gives a 7-row rolling average.
--   ROWS counts rows, so days with no activity would shorten the window; the
--   calendar join to dim_date guarantees one row per day.
-- Expected result: one row per day of the data window; the running total only
--   grows; the rolling average smooths weekday noise.
-- Performance: aggregate first (one row per day), then window over ~30 rows.
--   Windowing over raw facts would be far more expensive.
WITH bounds AS (
    SELECT MIN(date_key) AS first_key, MAX(date_key) AS last_key FROM fact_transactions
),
daily AS (
    SELECT
        d.full_date,
        COALESCE(SUM(CASE WHEN f.status = 'COMPLETED' THEN f.amount_mxn_minor END), 0) AS completed_minor
    FROM dim_date d
    CROSS JOIN bounds b
    LEFT JOIN fact_transactions f ON f.date_key = d.date_key
    WHERE d.date_key BETWEEN b.first_key AND b.last_key
    GROUP BY d.full_date
)
SELECT
    full_date,
    completed_minor,
    SUM(completed_minor) OVER (ORDER BY full_date ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)
        AS running_total_minor,
    CAST(AVG(completed_minor) OVER (ORDER BY full_date ROWS BETWEEN 6 PRECEDING AND CURRENT ROW) AS BIGINT)
        AS rolling_7d_avg_minor
FROM daily
ORDER BY full_date;
