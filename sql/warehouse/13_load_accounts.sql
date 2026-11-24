INSERT INTO dim_account (account_id, customer_id, account_type, currency_code, status, opened_at, updated_at, batch_id)
SELECT account_id, customer_id, account_type, currency_code, status, opened_at, updated_at, batch_id
FROM stg_accounts
ON CONFLICT (account_id) DO UPDATE
SET customer_id = EXCLUDED.customer_id,
    account_type = EXCLUDED.account_type,
    currency_code = EXCLUDED.currency_code,
    status = EXCLUDED.status,
    updated_at = EXCLUDED.updated_at,
    batch_id = EXCLUDED.batch_id
WHERE EXCLUDED.updated_at >= dim_account.updated_at;
