-- Financial reconciliation between the ETL star schema and the ELT tables.
-- Returns only the days that disagree on count, failures or MXN value:
-- an empty result means both paths produced the same numbers.
WITH etl AS (
    SELECT d.full_date AS txn_date,
           COUNT(*) AS transactions,
           SUM(CASE WHEN f.status = 'FAILED' THEN 1 ELSE 0 END) AS failed,
           SUM(f.amount_mxn_minor) AS gross_mxn_minor
    FROM fact_transactions f
    JOIN dim_date d ON d.date_key = f.date_key
    GROUP BY d.full_date
),
elt AS (
    SELECT txn_date,
           COUNT(*) AS transactions,
           SUM(CASE WHEN status = 'FAILED' THEN 1 ELSE 0 END) AS failed,
           SUM(amount_mxn_minor) AS gross_mxn_minor
    FROM elt_transactions
    GROUP BY txn_date
)
SELECT
    COALESCE(etl.txn_date, elt.txn_date) AS txn_date,
    etl.transactions AS etl_transactions,
    elt.transactions AS elt_transactions,
    etl.gross_mxn_minor AS etl_gross_mxn_minor,
    elt.gross_mxn_minor AS elt_gross_mxn_minor
FROM etl
FULL OUTER JOIN elt ON elt.txn_date = etl.txn_date
WHERE etl.transactions IS DISTINCT FROM elt.transactions
   OR etl.failed IS DISTINCT FROM elt.failed
   OR etl.gross_mxn_minor IS DISTINCT FROM elt.gross_mxn_minor
ORDER BY 1;
