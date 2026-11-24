-- ELT step 1: type and validate ONLY the raw rows that arrived after the ELT
-- watermark (incremental processing), entirely in SQL.
-- The rules mirror the Python/Pandera rules of the ETL path so the two can be
-- reconciled; unlike ETL, each record keeps only its *first* failing rule.
DROP TABLE IF EXISTS elt_work_checked;

CREATE TABLE elt_work_checked AS
WITH new_raw AS (
    SELECT *
    FROM stg_raw_transactions
    WHERE load_seq > (SELECT COALESCE(MAX(last_load_seq), 0) FROM elt_watermark WHERE entity = 'transactions')
),
typed AS (
    SELECT
        load_seq,
        batch_id,
        TRIM(transaction_id) AS transaction_id,
        TRIM(account_id) AS account_id,
        TRIM(customer_id) AS customer_id,
        NULLIF(TRIM(card_id), '') AS card_id,
        NULLIF(TRIM(merchant_id), '') AS merchant_id,
        NULLIF(TRIM(counterparty_account_id), '') AS counterparty_account_id,
        UPPER(TRIM(transaction_type)) AS transaction_type,
        UPPER(TRIM(currency_code)) AS currency_code,
        UPPER(TRIM(status)) AS status,
        UPPER(TRIM(channel)) AS channel,
        -- Validate the text first, then cast: neither engine may see an invalid cast.
        CASE WHEN TRIM(amount) ~ '^-?[0-9]{1,12}([.][0-9]{1,2})?$'
             THEN CAST(CAST(TRIM(amount) AS DECIMAL(16, 2)) * 100 AS BIGINT)
        END AS amount_minor,
        CASE WHEN TRIM(event_ts) ~ '^[0-9]{4}-(0[1-9]|1[0-2])-(0[1-9]|[12][0-9]|3[01])T([01][0-9]|2[0-3]):[0-5][0-9]:[0-5][0-9]Z$'
             THEN CAST(REPLACE(REPLACE(TRIM(event_ts), 'T', ' '), 'Z', '') AS TIMESTAMP)
        END AS event_ts,
        amount AS raw_amount,
        event_ts AS raw_event_ts
    FROM new_raw
),
checked AS (
    SELECT
        t.*,
        CASE
            WHEN t.transaction_id IS NULL THEN 'missing:transaction_id'
            WHEN t.account_id IS NULL THEN 'missing:account_id'
            WHEN t.customer_id IS NULL THEN 'missing:customer_id'
            -- A renamed field (schema drift) also arrives here as a NULL amount.
            WHEN t.raw_amount IS NULL THEN 'missing:amount'
            WHEN t.amount_minor IS NULL THEN 'invalid_format:amount'
            WHEN t.event_ts IS NULL THEN 'invalid_format:event_ts'
            WHEN NOT (t.transaction_id ~ '^T[0-9A-Z]{9,12}$') THEN 'transaction_id:str_matches'
            WHEN t.amount_minor <= 0 THEN 'amount:greater_than'
            WHEN t.currency_code NOT IN ('MXN', 'USD', 'EUR', 'CAD') THEN 'currency_code:isin'
            WHEN t.status NOT IN ('COMPLETED', 'FAILED', 'PENDING', 'REVERSED') THEN 'status:isin'
            WHEN t.transaction_type NOT IN ('PURCHASE', 'TRANSFER', 'WITHDRAWAL', 'DEPOSIT', 'FEE')
                THEN 'transaction_type:isin'
            WHEN t.channel NOT IN ('CARD_POS', 'ONLINE', 'ATM', 'BRANCH', 'MOBILE', 'SYSTEM') THEN 'channel:isin'
            WHEN t.transaction_type = 'TRANSFER' AND t.counterparty_account_id IS NULL
                THEN 'business:transfer_requires_counterparty'
            WHEN t.transaction_type = 'PURCHASE' AND t.merchant_id IS NULL
                THEN 'business:purchase_requires_merchant'
            WHEN a.account_id IS NULL THEN 'unknown_ref:account_id'
            WHEN NOT EXISTS (SELECT 1 FROM dim_customer c WHERE c.customer_id = t.customer_id)
                THEN 'unknown_ref:customer_id'
            WHEN t.merchant_id IS NOT NULL AND m.merchant_id IS NULL THEN 'unknown_ref:merchant_id'
            WHEN t.card_id IS NOT NULL AND k.card_id IS NULL THEN 'unknown_ref:card_id'
            WHEN a.customer_id <> t.customer_id THEN 'owner_mismatch'
            WHEN t.currency_code <> 'MXN' AND r.rate_micros IS NULL THEN 'missing_exchange_rate'
        END AS rejection_reason,
        CASE WHEN t.currency_code = 'MXN' THEN 1000000 ELSE r.rate_micros END AS rate_micros
    FROM typed t
    LEFT JOIN dim_account a ON a.account_id = t.account_id
    LEFT JOIN dim_merchant m ON m.merchant_id = t.merchant_id
    LEFT JOIN dim_card k ON k.card_id = t.card_id
    LEFT JOIN ref_exchange_rate r
           ON r.currency_code = t.currency_code AND r.rate_date = CAST(t.event_ts AS DATE)
)
SELECT
    c.*,
    -- First valid occurrence of a transaction_id within the new rows wins;
    -- invalid rows are numbered separately so they never shadow a valid one.
    ROW_NUMBER() OVER (
        PARTITION BY c.transaction_id, (c.rejection_reason IS NULL)
        ORDER BY c.load_seq
    ) AS occurrence
FROM checked c;
