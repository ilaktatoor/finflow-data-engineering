-- ELT staging area. Raw transactions land here *untyped* (every field VARCHAR,
-- exactly as the producer sent it); SQL does the rest inside the warehouse.

CREATE SEQUENCE IF NOT EXISTS seq_raw_load;

-- Grain: one row per raw record received (duplicates and invalid records included).
CREATE TABLE IF NOT EXISTS stg_raw_transactions (
    load_seq                BIGINT PRIMARY KEY DEFAULT nextval('seq_raw_load'),
    batch_id                VARCHAR(40) NOT NULL,
    record_position         INTEGER NOT NULL,
    transaction_id          VARCHAR,
    account_id              VARCHAR,
    customer_id             VARCHAR,
    card_id                 VARCHAR,
    merchant_id             VARCHAR,
    counterparty_account_id VARCHAR,
    transaction_type        VARCHAR,
    amount                  VARCHAR,
    currency_code           VARCHAR,
    status                  VARCHAR,
    channel                 VARCHAR,
    event_ts                VARCHAR,
    raw_record              VARCHAR NOT NULL,
    loaded_at               TIMESTAMP NOT NULL,
    UNIQUE (batch_id, record_position)
);

-- Grain: one row per valid transaction_id (latest version), built by SQL.
CREATE TABLE IF NOT EXISTS elt_transactions (
    transaction_id    VARCHAR(16) PRIMARY KEY,
    account_id        VARCHAR(10) NOT NULL,
    customer_id       VARCHAR(10) NOT NULL,
    merchant_id       VARCHAR(10),
    transaction_type  VARCHAR(20) NOT NULL,
    currency_code     VARCHAR(3) NOT NULL,
    status            VARCHAR(10) NOT NULL,
    amount_minor      BIGINT NOT NULL,
    amount_mxn_minor  BIGINT NOT NULL,
    event_ts          TIMESTAMP NOT NULL,
    txn_date          DATE NOT NULL,
    batch_id          VARCHAR(40) NOT NULL,
    load_seq          BIGINT NOT NULL
);

-- Grain: one row per rejected or duplicate raw record.
CREATE TABLE IF NOT EXISTS elt_rejected_transactions (
    load_seq         BIGINT PRIMARY KEY,
    batch_id         VARCHAR(40) NOT NULL,
    transaction_id   VARCHAR,
    rejection_reason VARCHAR(40) NOT NULL
);

-- Grain: one row per ELT entity: the last raw load_seq already transformed.
CREATE TABLE IF NOT EXISTS elt_watermark (
    entity        VARCHAR(30) PRIMARY KEY,
    last_load_seq BIGINT NOT NULL,
    updated_at    TIMESTAMP NOT NULL
);
