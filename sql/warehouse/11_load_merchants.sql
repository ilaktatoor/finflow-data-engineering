-- SCD Type 1: overwrite in place, but never let an older record replace a newer one.
INSERT INTO dim_merchant (merchant_id, merchant_name, category, city, updated_at, batch_id)
SELECT merchant_id, merchant_name, category, city, updated_at, batch_id
FROM stg_merchants
ON CONFLICT (merchant_id) DO UPDATE
SET merchant_name = EXCLUDED.merchant_name,
    category = EXCLUDED.category,
    city = EXCLUDED.city,
    updated_at = EXCLUDED.updated_at,
    batch_id = EXCLUDED.batch_id
WHERE EXCLUDED.updated_at >= dim_merchant.updated_at;
