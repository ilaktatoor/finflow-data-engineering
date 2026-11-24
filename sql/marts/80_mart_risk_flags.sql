-- Transactions flagged by the SIMULATED risk rules (not a fraud model).
DROP TABLE IF EXISTS mart_risk_flags;
CREATE TABLE mart_risk_flags AS
SELECT
    f.transaction_id,
    f.event_ts,
    a.account_id,
    c.customer_id,
    tt.code AS transaction_type,
    f.amount_mxn_minor,
    f.risk_reasons
FROM fact_transactions f
JOIN dim_account a ON a.account_key = f.account_key
JOIN dim_customer c ON c.customer_key = f.customer_key
JOIN dim_transaction_type tt ON tt.transaction_type_key = f.transaction_type_key
WHERE f.is_risk_flagged;
