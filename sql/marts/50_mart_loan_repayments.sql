-- Monthly loan repayment volume and delinquency.
DROP TABLE IF EXISTS mart_loan_repayments;
CREATE TABLE mart_loan_repayments AS
SELECT
    d.year,
    d.month,
    COUNT(*) AS installments_due,
    CAST(SUM(CASE WHEN p.status = 'ON_TIME' THEN 1 ELSE 0 END) AS BIGINT) AS on_time,
    CAST(SUM(CASE WHEN p.status = 'LATE' THEN 1 ELSE 0 END) AS BIGINT) AS late,
    CAST(SUM(CASE WHEN p.status = 'MISSED' THEN 1 ELSE 0 END) AS BIGINT) AS missed,
    CAST(SUM(p.amount_paid_minor) AS BIGINT) AS paid_minor,
    CAST(SUM(p.principal_minor) AS BIGINT) AS principal_minor,
    CAST(SUM(p.interest_minor) AS BIGINT) AS interest_minor
FROM fact_loan_payments p
JOIN dim_date d ON d.date_key = p.due_date_key
GROUP BY d.year, d.month;
