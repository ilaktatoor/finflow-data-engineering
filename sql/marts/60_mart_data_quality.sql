-- Which rules fail most often, and how many records are rejected per batch.
DROP TABLE IF EXISTS mart_data_quality_rules;
CREATE TABLE mart_data_quality_rules AS
SELECT
    entity,
    rule_name,
    dimension,
    COUNT(DISTINCT batch_id) AS batches_evaluated,
    CAST(SUM(failed_records) AS BIGINT) AS failed_records,
    CAST(SUM(checked_records) AS BIGINT) AS checked_records
FROM fact_data_quality
WHERE rule_name NOT IN ('reject_rate', 'reconciliation', 'freshness_lag_hours')
GROUP BY entity, rule_name, dimension;

DROP TABLE IF EXISTS mart_batch_quality;
CREATE TABLE mart_batch_quality AS
SELECT
    q.batch_id,
    b.status AS batch_status,
    q.entity,
    q.checked_records AS input_records,
    q.failed_records AS rejected_records,
    q.measured_value AS reject_rate,
    q.severity
FROM fact_data_quality q
LEFT JOIN etl_batch b ON b.batch_id = q.batch_id
WHERE q.rule_name = 'reject_rate';
