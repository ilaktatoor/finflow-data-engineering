-- PostgreSQL only: DuckDB has no materialized views (a CREATE TABLE AS that you
-- rebuild, like the marts in sql/marts, is the DuckDB equivalent).
-- Business question: Serve a daily summary instantly to a dashboard, refreshing
--   it only when new data has been loaded.
-- Explanation: a materialized view stores the result. Reads are cheap; data is
--   as fresh as the last REFRESH. REFRESH ... CONCURRENTLY needs a unique index
--   and lets readers keep reading during the refresh.
-- Expected result: one row per day; identical to mart_daily_transactions.
-- Performance: trades storage and staleness for read speed.
CREATE MATERIALIZED VIEW mv_daily_value AS
SELECT d.full_date, COUNT(*) AS transactions, SUM(f.amount_mxn_minor) AS gross_mxn_minor
FROM fact_transactions f
JOIN dim_date d ON d.date_key = f.date_key
GROUP BY d.full_date;
CREATE UNIQUE INDEX ux_mv_daily_value ON mv_daily_value (full_date);
REFRESH MATERIALIZED VIEW mv_daily_value;
SELECT * FROM mv_daily_value ORDER BY full_date LIMIT 10;
