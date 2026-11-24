-- Load transactions, resolving surrogate keys.
-- The customer key is resolved *point in time*: the SCD2 version that was valid
-- when the transaction happened, not the current one.
-- Upsert on the natural key makes reruns idempotent and lets a later batch
-- correct a status (e.g. PENDING -> COMPLETED). The batch guard stops a replay
-- of an older batch from overwriting a newer correction.
INSERT INTO fact_transactions (
    transaction_id, date_key, customer_key, account_key, card_key, merchant_key,
    transaction_type_key, currency_key, counterparty_account_id, amount_minor,
    amount_mxn_minor, rate_micros, status, channel, event_ts, is_late_arriving,
    is_risk_flagged, risk_reasons, batch_id, loaded_at
)
SELECT
    s.transaction_id, s.date_key, c.customer_key, a.account_key, k.card_key, m.merchant_key,
    t.transaction_type_key, cu.currency_key, s.counterparty_account_id, s.amount_minor,
    s.amount_mxn_minor, s.rate_micros, s.status, s.channel, s.event_ts, s.is_late_arriving,
    s.is_risk_flagged, s.risk_reasons, s.batch_id, s.loaded_at
FROM stg_transactions s
JOIN dim_account a ON a.account_id = s.account_id
JOIN dim_customer c
  ON c.customer_id = s.customer_id
 AND s.event_ts >= c.valid_from
 AND (c.valid_to IS NULL OR s.event_ts < c.valid_to)
JOIN dim_transaction_type t ON t.code = s.transaction_type
JOIN dim_currency cu ON cu.currency_code = s.currency_code
LEFT JOIN dim_card k ON k.card_id = s.card_id
LEFT JOIN dim_merchant m ON m.merchant_id = s.merchant_id
ON CONFLICT (transaction_id) DO UPDATE
SET date_key = EXCLUDED.date_key,
    customer_key = EXCLUDED.customer_key,
    account_key = EXCLUDED.account_key,
    card_key = EXCLUDED.card_key,
    merchant_key = EXCLUDED.merchant_key,
    transaction_type_key = EXCLUDED.transaction_type_key,
    currency_key = EXCLUDED.currency_key,
    counterparty_account_id = EXCLUDED.counterparty_account_id,
    amount_minor = EXCLUDED.amount_minor,
    amount_mxn_minor = EXCLUDED.amount_mxn_minor,
    rate_micros = EXCLUDED.rate_micros,
    status = EXCLUDED.status,
    channel = EXCLUDED.channel,
    event_ts = EXCLUDED.event_ts,
    is_late_arriving = EXCLUDED.is_late_arriving,
    is_risk_flagged = EXCLUDED.is_risk_flagged,
    risk_reasons = EXCLUDED.risk_reasons,
    batch_id = EXCLUDED.batch_id,
    loaded_at = EXCLUDED.loaded_at
WHERE EXCLUDED.batch_id >= fact_transactions.batch_id;
