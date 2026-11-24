-- ELT step 2: upsert valid rows and record rejects/duplicates, then advance the
-- ELT watermark. The caller runs steps 1-2 in a single transaction.
INSERT INTO elt_transactions (
    transaction_id, account_id, customer_id, merchant_id, transaction_type, currency_code, status,
    amount_minor, amount_mxn_minor, event_ts, txn_date, batch_id, load_seq
)
SELECT
    transaction_id, account_id, customer_id, merchant_id, transaction_type, currency_code, status,
    amount_minor,
    -- Integer half-up rounding, identical to finflow.common.money.convert_minor for the
    -- positive amounts that pass validation. Integer division on both engines.
    (amount_minor * rate_micros + 500000) / 1000000,
    event_ts, CAST(event_ts AS DATE), batch_id, load_seq
FROM elt_work_checked
WHERE rejection_reason IS NULL AND occurrence = 1
ON CONFLICT (transaction_id) DO UPDATE
SET status = EXCLUDED.status,
    amount_minor = EXCLUDED.amount_minor,
    amount_mxn_minor = EXCLUDED.amount_mxn_minor,
    event_ts = EXCLUDED.event_ts,
    txn_date = EXCLUDED.txn_date,
    batch_id = EXCLUDED.batch_id,
    load_seq = EXCLUDED.load_seq
WHERE EXCLUDED.load_seq > elt_transactions.load_seq;

INSERT INTO elt_rejected_transactions (load_seq, batch_id, transaction_id, rejection_reason)
SELECT load_seq, batch_id, transaction_id, COALESCE(rejection_reason, 'duplicate')
FROM elt_work_checked
WHERE rejection_reason IS NOT NULL OR occurrence > 1
ON CONFLICT (load_seq) DO NOTHING;

INSERT INTO elt_watermark (entity, last_load_seq, updated_at)
SELECT 'transactions', MAX(load_seq), CURRENT_TIMESTAMP
FROM elt_work_checked
HAVING MAX(load_seq) IS NOT NULL
ON CONFLICT (entity) DO UPDATE
SET last_load_seq = EXCLUDED.last_load_seq,
    updated_at = EXCLUDED.updated_at;
