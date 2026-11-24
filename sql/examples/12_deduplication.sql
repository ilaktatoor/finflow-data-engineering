-- Business question: Which raw records were sent more than once, and which copy
--   should be kept?
-- Explanation: the ELT staging table keeps every raw record, duplicates
--   included. ROW_NUMBER over the business key ranks the copies; keeping
--   rn = 1 is the standard SQL deduplication pattern. DISTINCT would not work:
--   it compares whole rows, and copies differ in load_seq/batch_id.
-- Expected result: the transaction_ids received more than once with their
--   copies; injected duplicates and status corrections appear here.
-- Performance: one sort by the key; with many duplicates, an index on the key
--   makes the GROUP BY ... HAVING check cheaper than the full window.
WITH copies AS (
    SELECT
        transaction_id,
        batch_id,
        load_seq,
        status,
        ROW_NUMBER() OVER (PARTITION BY transaction_id ORDER BY load_seq DESC) AS rn,
        COUNT(*) OVER (PARTITION BY transaction_id) AS copies
    FROM stg_raw_transactions
    WHERE transaction_id IS NOT NULL
)
SELECT transaction_id, batch_id, load_seq, status, rn, rn = 1 AS kept_as_latest
FROM copies
WHERE copies > 1
ORDER BY transaction_id, rn;
