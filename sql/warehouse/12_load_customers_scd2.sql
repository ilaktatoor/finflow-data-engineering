-- SCD Type 2 for customers.
-- A change in any descriptive attribute (detected through attributes_hash)
-- closes the current version and opens a new one, so facts keep pointing at
-- the customer exactly as they were when the transaction happened.

-- 1. Close current versions whose attributes changed. valid_to is exclusive.
UPDATE dim_customer
SET valid_to = s.updated_at,
    is_current = FALSE
FROM stg_customers s
WHERE dim_customer.customer_id = s.customer_id
  AND dim_customer.is_current
  AND dim_customer.attributes_hash <> s.attributes_hash
  AND s.updated_at > dim_customer.valid_from;

-- 2. Open a version for brand-new customers and for the ones closed above.
--    The first version starts at 1900-01-01 so it covers every historical fact.
INSERT INTO dim_customer (
    customer_id, first_name, last_name, email, city, state, segment, customer_since,
    attributes_hash, valid_from, valid_to, is_current, batch_id
)
SELECT
    s.customer_id, s.first_name, s.last_name, s.email, s.city, s.state, s.segment, s.created_at,
    s.attributes_hash,
    CASE WHEN EXISTS (SELECT 1 FROM dim_customer d WHERE d.customer_id = s.customer_id)
         THEN s.updated_at
         ELSE TIMESTAMP '1900-01-01 00:00:00'
    END,
    NULL, TRUE, s.batch_id
FROM stg_customers s
WHERE NOT EXISTS (
    SELECT 1 FROM dim_customer d WHERE d.customer_id = s.customer_id AND d.is_current
);
