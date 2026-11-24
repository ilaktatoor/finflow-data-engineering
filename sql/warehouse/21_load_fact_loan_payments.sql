-- One row per installment. The customer version is the one valid on the
-- payment's effective date (paid date, or due date when it was missed).
INSERT INTO fact_loan_payments (
    payment_id, loan_key, customer_key, due_date_key, paid_date_key, installment_number,
    amount_paid_minor, principal_minor, interest_minor, status, days_late, batch_id, loaded_at
)
SELECT
    s.payment_id, l.loan_key, c.customer_key, s.due_date_key, s.paid_date_key, s.installment_number,
    s.amount_minor, s.principal_component_minor, s.interest_component_minor, s.status, s.days_late,
    s.batch_id, s.loaded_at
FROM stg_loan_payments s
JOIN dim_loan l ON l.loan_id = s.loan_id
JOIN dim_customer c
  ON c.customer_id = l.customer_id
 AND s.effective_ts >= c.valid_from
 AND (c.valid_to IS NULL OR s.effective_ts < c.valid_to)
ON CONFLICT (payment_id) DO UPDATE
SET paid_date_key = EXCLUDED.paid_date_key,
    amount_paid_minor = EXCLUDED.amount_paid_minor,
    principal_minor = EXCLUDED.principal_minor,
    interest_minor = EXCLUDED.interest_minor,
    status = EXCLUDED.status,
    days_late = EXCLUDED.days_late,
    batch_id = EXCLUDED.batch_id,
    loaded_at = EXCLUDED.loaded_at
WHERE EXCLUDED.batch_id >= fact_loan_payments.batch_id;
