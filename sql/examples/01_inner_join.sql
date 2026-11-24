-- Business question: What did each completed card purchase buy, and from whom?
-- Explanation: INNER JOIN keeps only facts that have a matching merchant and
--   type. Transfers, deposits and fees have no merchant, so they drop out.
-- Expected result: one row per completed PURCHASE (roughly 55-60% of all
--   transactions in the small profile), newest first.
-- Performance: the joins are on surrogate keys (small integers). Dimensions are
--   tiny, so engines build a hash table on the dimension and stream the fact.
SELECT
    f.transaction_id,
    f.event_ts,
    m.merchant_name,
    m.category,
    f.amount_mxn_minor / 100.0 AS amount_mxn
FROM fact_transactions f
INNER JOIN dim_merchant m ON m.merchant_key = f.merchant_key
INNER JOIN dim_transaction_type t ON t.transaction_type_key = f.transaction_type_key
WHERE t.code = 'PURCHASE'
  AND f.status = 'COMPLETED'
ORDER BY f.event_ts DESC
LIMIT 20;
