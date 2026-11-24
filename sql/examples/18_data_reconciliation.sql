-- Business question: Do all records received for a batch reconcile with what
--   was accepted, rejected or dropped as duplicates?
-- Explanation: every input record must end up accepted, rejected or flagged
--   as a duplicate (input = accepted + rejected + duplicates). The pipeline
--   checks this per entity and records the outcome as the 'reconciliation'
--   rule; conditional aggregation lays the measurements out per batch.
--   accepted is derived here, the pipeline counts it independently.
-- Expected result: one row per batch with reconciliation_failures = 0.
-- Performance: tiny aggregates over the quality fact; run it after every load.
SELECT
    q.batch_id,
    MAX(CASE WHEN q.rule_name = 'reject_rate' THEN q.checked_records END) AS input_records,
    MAX(CASE WHEN q.rule_name = 'reject_rate' THEN q.failed_records END) AS rejected,
    MAX(CASE WHEN q.rule_name = 'duplicate' THEN q.failed_records END) AS duplicates,
    MAX(CASE WHEN q.rule_name = 'reject_rate' THEN q.checked_records END)
      - MAX(CASE WHEN q.rule_name = 'reject_rate' THEN q.failed_records END)
      - MAX(CASE WHEN q.rule_name = 'duplicate' THEN q.failed_records END) AS accepted,
    MAX(CASE WHEN q.rule_name = 'reconciliation' THEN q.failed_records END) AS reconciliation_failures
FROM fact_data_quality q
WHERE q.entity = 'transactions'
GROUP BY q.batch_id
ORDER BY q.batch_id;
