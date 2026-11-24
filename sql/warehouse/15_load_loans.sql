INSERT INTO dim_loan (
    loan_id, customer_id, account_id, principal_minor, annual_rate_micros, term_months,
    currency_code, status, disbursed_at, updated_at, batch_id
)
SELECT loan_id, customer_id, account_id, principal_minor, annual_rate_micros, term_months,
       currency_code, status, disbursed_at, updated_at, batch_id
FROM stg_loans
ON CONFLICT (loan_id) DO UPDATE
SET principal_minor = EXCLUDED.principal_minor,
    annual_rate_micros = EXCLUDED.annual_rate_micros,
    term_months = EXCLUDED.term_months,
    status = EXCLUDED.status,
    updated_at = EXCLUDED.updated_at,
    batch_id = EXCLUDED.batch_id
WHERE EXCLUDED.updated_at >= dim_loan.updated_at;
