-- PostgreSQL-only additions. DuckDB has no partial indexes, so the
-- "one current version per customer" rule is enforced only here; on DuckDB the
-- SCD2 load SQL guarantees it and tests/integration check it.
CREATE UNIQUE INDEX IF NOT EXISTS ux_dim_customer_current
    ON dim_customer (customer_id) WHERE is_current;

-- Composite index for "transactions of an account over time" lookups.
CREATE INDEX IF NOT EXISTS ix_fact_transactions_account_ts
    ON fact_transactions (account_key, event_ts);
