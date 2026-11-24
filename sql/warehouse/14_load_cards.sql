INSERT INTO dim_card (card_id, account_id, network, card_last4, credit_limit_minor, status, issued_at, updated_at, batch_id)
SELECT card_id, account_id, network, card_last4, credit_limit_minor, status, issued_at, updated_at, batch_id
FROM stg_cards
ON CONFLICT (card_id) DO UPDATE
SET account_id = EXCLUDED.account_id,
    network = EXCLUDED.network,
    card_last4 = EXCLUDED.card_last4,
    credit_limit_minor = EXCLUDED.credit_limit_minor,
    status = EXCLUDED.status,
    updated_at = EXCLUDED.updated_at,
    batch_id = EXCLUDED.batch_id
WHERE EXCLUDED.updated_at >= dim_card.updated_at;
