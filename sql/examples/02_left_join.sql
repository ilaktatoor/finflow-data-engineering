-- Business question: Which accounts had no transactions at all in the period?
-- Explanation: LEFT JOIN keeps every account; accounts without facts get NULLs
--   on the fact side, which the WHERE clause then selects (an "anti-join").
-- Expected result: a small number of dormant accounts (random activity leaves
--   some of the 150 accounts unused); zero rows is also a valid outcome.
-- Performance: equivalent to NOT EXISTS; both engines plan it as an anti-join.
--   Filtering on the fact column inside WHERE would turn it back into an inner join.
SELECT
    a.account_id,
    a.customer_id,
    a.account_type,
    a.currency_code
FROM dim_account a
LEFT JOIN fact_transactions f ON f.account_key = a.account_key
WHERE f.transaction_id IS NULL
ORDER BY a.account_id;
