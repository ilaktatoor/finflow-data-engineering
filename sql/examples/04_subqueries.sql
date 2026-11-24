-- Business question: Which transactions are larger than the average for their
--   transaction type?
-- Explanation: a correlated subquery computes the per-type average for each
--   outer row. The second form (scalar subquery in SELECT) shows the share of
--   the type's total.
-- Expected result: the above-average transactions; lognormal amounts mean
--   roughly a third of rows exceed their type's mean.
-- Performance: modern planners decorrelate this into a join with a grouped
--   aggregate; on engines that do not, a correlated subquery runs once per row.
--   Compare with 08_window_functions.sql, which avoids the self-reference.
SELECT
    f.transaction_id,
    t.code AS transaction_type,
    f.amount_mxn_minor,
    ROUND(100.0 * f.amount_mxn_minor / (
        SELECT SUM(f2.amount_mxn_minor) FROM fact_transactions f2
        WHERE f2.transaction_type_key = f.transaction_type_key
    ), 4) AS pct_of_type_total
FROM fact_transactions f
JOIN dim_transaction_type t ON t.transaction_type_key = f.transaction_type_key
WHERE f.amount_mxn_minor > (
    SELECT AVG(f2.amount_mxn_minor) FROM fact_transactions f2
    WHERE f2.transaction_type_key = f.transaction_type_key
)
ORDER BY f.amount_mxn_minor DESC
LIMIT 20;
