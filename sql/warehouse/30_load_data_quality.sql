-- Replace this batch's quality measurements (re-evaluation must not duplicate them).
DELETE FROM fact_data_quality
WHERE batch_id IN (SELECT DISTINCT batch_id FROM stg_data_quality);

INSERT INTO fact_data_quality (
    batch_id, entity, rule_name, dimension, severity, failed_records, checked_records,
    measured_value, run_id, measured_at
)
SELECT batch_id, entity, rule_name, dimension, severity, failed_records, checked_records,
       measured_value, run_id, measured_at
FROM stg_data_quality;
