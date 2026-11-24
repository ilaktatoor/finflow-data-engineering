-- Built from the ELT tables only: the same business question answered by the
-- SQL-first path, used for ETL-vs-ELT reconciliation.
DROP TABLE IF EXISTS mart_elt_daily_summary;
CREATE TABLE mart_elt_daily_summary AS
SELECT
    txn_date,
    COUNT(*) AS transactions,
    CAST(SUM(CASE WHEN status = 'FAILED' THEN 1 ELSE 0 END) AS BIGINT) AS failed,
    CAST(SUM(amount_mxn_minor) AS BIGINT) AS gross_mxn_minor
FROM elt_transactions
GROUP BY txn_date;
