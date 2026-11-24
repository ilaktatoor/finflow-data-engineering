-- Step durations: how long does each pipeline step take, and how often does it fail?
DROP TABLE IF EXISTS mart_pipeline_performance;
CREATE TABLE mart_pipeline_performance AS
SELECT
    pipeline,
    step,
    COUNT(*) AS executions,
    CAST(SUM(CASE WHEN status = 'FAILED' THEN 1 ELSE 0 END) AS BIGINT) AS failures,
    MIN(duration_ms) AS min_ms,
    CAST(AVG(duration_ms) AS BIGINT) AS avg_ms,
    MAX(duration_ms) AS max_ms
FROM fact_pipeline_execution
GROUP BY pipeline, step;
