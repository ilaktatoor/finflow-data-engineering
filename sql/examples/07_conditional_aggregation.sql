-- Business question: For each channel, how many transactions completed,
--   failed, stayed pending or were reversed, and what is the failure rate?
-- Explanation: conditional aggregation (SUM over CASE) pivots statuses into
--   columns in a single pass, instead of one query per status.
-- Expected result: one row per channel (6); failure rates around the
--   generator's 6% FAILED share, varying by channel because volumes are small.
-- Performance: one scan, one hash aggregate. FILTER (WHERE ...) is an
--   equivalent syntax supported by both engines.
SELECT
    f.channel,
    COUNT(*) AS total,
    SUM(CASE WHEN f.status = 'COMPLETED' THEN 1 ELSE 0 END) AS completed,
    SUM(CASE WHEN f.status = 'FAILED' THEN 1 ELSE 0 END) AS failed,
    SUM(CASE WHEN f.status = 'PENDING' THEN 1 ELSE 0 END) AS pending,
    SUM(CASE WHEN f.status = 'REVERSED' THEN 1 ELSE 0 END) AS reversed,
    COUNT(*) FILTER (WHERE f.is_risk_flagged) AS risk_flagged,
    ROUND(100.0 * SUM(CASE WHEN f.status = 'FAILED' THEN 1 ELSE 0 END) / COUNT(*), 2) AS failure_pct
FROM fact_transactions f
GROUP BY f.channel
ORDER BY total DESC;
