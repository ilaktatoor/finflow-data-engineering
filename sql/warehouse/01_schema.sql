-- FinFlow warehouse: star schema shared by DuckDB and PostgreSQL.
-- Idempotent: safe to run on every pipeline start.
-- Money is BIGINT minor units (cents); exchange rates are BIGINT micros (x 1,000,000).

CREATE SEQUENCE IF NOT EXISTS seq_customer_key;
CREATE SEQUENCE IF NOT EXISTS seq_account_key;
CREATE SEQUENCE IF NOT EXISTS seq_card_key;
CREATE SEQUENCE IF NOT EXISTS seq_merchant_key;
CREATE SEQUENCE IF NOT EXISTS seq_loan_key;
CREATE SEQUENCE IF NOT EXISTS seq_execution_id;

-- ---------------------------------------------------------------- dimensions

-- Grain: one row per calendar day.
CREATE TABLE IF NOT EXISTS dim_date (
    date_key      INTEGER PRIMARY KEY,          -- YYYYMMDD, readable and sortable
    full_date     DATE NOT NULL UNIQUE,
    year          SMALLINT NOT NULL,
    quarter       SMALLINT NOT NULL,
    month         SMALLINT NOT NULL,
    month_name    VARCHAR(10) NOT NULL,
    day_of_month  SMALLINT NOT NULL,
    iso_day_of_week SMALLINT NOT NULL,           -- 1 = Monday
    is_weekend    BOOLEAN NOT NULL
);

-- Grain: one row per ISO currency.
CREATE TABLE IF NOT EXISTS dim_currency (
    currency_key  SMALLINT PRIMARY KEY,
    currency_code VARCHAR(3) NOT NULL UNIQUE,
    currency_name VARCHAR(40) NOT NULL,
    minor_unit    SMALLINT NOT NULL
);
INSERT INTO dim_currency VALUES
    (1, 'MXN', 'Mexican peso', 2),
    (2, 'USD', 'US dollar', 2),
    (3, 'EUR', 'Euro', 2),
    (4, 'CAD', 'Canadian dollar', 2)
ON CONFLICT DO NOTHING;

-- Grain: one row per transaction type.
CREATE TABLE IF NOT EXISTS dim_transaction_type (
    transaction_type_key SMALLINT PRIMARY KEY,
    code        VARCHAR(20) NOT NULL UNIQUE,
    description VARCHAR(80) NOT NULL,
    direction   VARCHAR(6) NOT NULL CHECK (direction IN ('DEBIT', 'CREDIT'))
);
INSERT INTO dim_transaction_type VALUES
    (1, 'PURCHASE', 'Card purchase at a merchant', 'DEBIT'),
    (2, 'TRANSFER', 'Transfer to another account', 'DEBIT'),
    (3, 'WITHDRAWAL', 'Cash withdrawal', 'DEBIT'),
    (4, 'DEPOSIT', 'Cash or cheque deposit', 'CREDIT'),
    (5, 'FEE', 'Bank fee', 'DEBIT')
ON CONFLICT DO NOTHING;

-- Grain: one row per customer *version* (SCD Type 2).
-- valid_to is exclusive; the current version has valid_to NULL and is_current TRUE.
CREATE TABLE IF NOT EXISTS dim_customer (
    customer_key    BIGINT PRIMARY KEY DEFAULT nextval('seq_customer_key'),
    customer_id     VARCHAR(10) NOT NULL,
    first_name      VARCHAR(80) NOT NULL,
    last_name       VARCHAR(80) NOT NULL,
    email           VARCHAR(120),
    city            VARCHAR(80),
    state           VARCHAR(80),
    segment         VARCHAR(10) NOT NULL,
    customer_since  TIMESTAMP NOT NULL,
    attributes_hash VARCHAR(24) NOT NULL,
    valid_from      TIMESTAMP NOT NULL,
    valid_to        TIMESTAMP,
    is_current      BOOLEAN NOT NULL,
    batch_id        VARCHAR(40) NOT NULL,
    UNIQUE (customer_id, valid_from)
);

-- Grain: one row per account (SCD Type 1: corrections overwrite).
CREATE TABLE IF NOT EXISTS dim_account (
    account_key   BIGINT PRIMARY KEY DEFAULT nextval('seq_account_key'),
    account_id    VARCHAR(10) NOT NULL UNIQUE,
    customer_id   VARCHAR(10) NOT NULL,
    account_type  VARCHAR(10) NOT NULL,
    currency_code VARCHAR(3) NOT NULL,
    status        VARCHAR(10) NOT NULL,
    opened_at     TIMESTAMP NOT NULL,
    updated_at    TIMESTAMP NOT NULL,
    batch_id      VARCHAR(40) NOT NULL
);

-- Grain: one row per card (SCD Type 1). No card numbers are stored, only the last 4 digits.
CREATE TABLE IF NOT EXISTS dim_card (
    card_key           BIGINT PRIMARY KEY DEFAULT nextval('seq_card_key'),
    card_id            VARCHAR(10) NOT NULL UNIQUE,
    account_id         VARCHAR(10) NOT NULL,
    network            VARCHAR(12) NOT NULL,
    card_last4         VARCHAR(4),
    credit_limit_minor BIGINT NOT NULL,
    status             VARCHAR(10) NOT NULL,
    issued_at          TIMESTAMP NOT NULL,
    updated_at         TIMESTAMP NOT NULL,
    batch_id           VARCHAR(40) NOT NULL
);

-- Grain: one row per merchant (SCD Type 1).
CREATE TABLE IF NOT EXISTS dim_merchant (
    merchant_key  BIGINT PRIMARY KEY DEFAULT nextval('seq_merchant_key'),
    merchant_id   VARCHAR(10) NOT NULL UNIQUE,
    merchant_name VARCHAR(120) NOT NULL,
    category      VARCHAR(20) NOT NULL,
    city          VARCHAR(80),
    updated_at    TIMESTAMP NOT NULL,
    batch_id      VARCHAR(40) NOT NULL
);

-- Grain: one row per loan (SCD Type 1).
CREATE TABLE IF NOT EXISTS dim_loan (
    loan_key           BIGINT PRIMARY KEY DEFAULT nextval('seq_loan_key'),
    loan_id            VARCHAR(10) NOT NULL UNIQUE,
    customer_id        VARCHAR(10) NOT NULL,
    account_id         VARCHAR(10) NOT NULL,
    principal_minor    BIGINT NOT NULL,
    annual_rate_micros BIGINT NOT NULL,
    term_months        SMALLINT NOT NULL,
    currency_code      VARCHAR(3) NOT NULL,
    status             VARCHAR(10) NOT NULL,
    disbursed_at       TIMESTAMP NOT NULL,
    updated_at         TIMESTAMP NOT NULL,
    batch_id           VARCHAR(40) NOT NULL
);

-- Grain: one rate per foreign currency per day (rate to MXN).
CREATE TABLE IF NOT EXISTS ref_exchange_rate (
    currency_code VARCHAR(3) NOT NULL,
    rate_date     DATE NOT NULL,
    rate_micros   BIGINT NOT NULL CHECK (rate_micros > 0),
    batch_id      VARCHAR(40) NOT NULL,
    PRIMARY KEY (currency_code, rate_date)
);

-- ---------------------------------------------------------------------- facts

-- Grain: one row per transaction_id (the latest known state of the transaction).
CREATE TABLE IF NOT EXISTS fact_transactions (
    transaction_id          VARCHAR(16) PRIMARY KEY,
    date_key                INTEGER NOT NULL REFERENCES dim_date (date_key),
    customer_key            BIGINT NOT NULL REFERENCES dim_customer (customer_key),
    account_key             BIGINT NOT NULL REFERENCES dim_account (account_key),
    card_key                BIGINT REFERENCES dim_card (card_key),
    merchant_key            BIGINT REFERENCES dim_merchant (merchant_key),
    transaction_type_key    SMALLINT NOT NULL REFERENCES dim_transaction_type (transaction_type_key),
    currency_key            SMALLINT NOT NULL REFERENCES dim_currency (currency_key),
    counterparty_account_id VARCHAR(10),
    amount_minor            BIGINT NOT NULL CHECK (amount_minor > 0),
    amount_mxn_minor        BIGINT NOT NULL CHECK (amount_mxn_minor > 0),
    rate_micros             BIGINT NOT NULL,
    status                  VARCHAR(10) NOT NULL
        CHECK (status IN ('COMPLETED', 'FAILED', 'PENDING', 'REVERSED')),
    channel                 VARCHAR(10) NOT NULL,
    event_ts                TIMESTAMP NOT NULL,
    is_late_arriving        BOOLEAN NOT NULL,
    is_risk_flagged         BOOLEAN NOT NULL,
    risk_reasons            VARCHAR(60),
    batch_id                VARCHAR(40) NOT NULL,
    loaded_at               TIMESTAMP NOT NULL
);

-- Grain: one row per loan installment (payment_id).
CREATE TABLE IF NOT EXISTS fact_loan_payments (
    payment_id          VARCHAR(12) PRIMARY KEY,
    loan_key            BIGINT NOT NULL REFERENCES dim_loan (loan_key),
    customer_key        BIGINT NOT NULL REFERENCES dim_customer (customer_key),
    due_date_key        INTEGER NOT NULL REFERENCES dim_date (date_key),
    paid_date_key       INTEGER REFERENCES dim_date (date_key),
    installment_number  SMALLINT NOT NULL,
    amount_paid_minor   BIGINT NOT NULL CHECK (amount_paid_minor >= 0),
    principal_minor     BIGINT NOT NULL,
    interest_minor      BIGINT NOT NULL,
    status              VARCHAR(8) NOT NULL CHECK (status IN ('ON_TIME', 'LATE', 'MISSED')),
    days_late           INTEGER,
    batch_id            VARCHAR(40) NOT NULL,
    loaded_at           TIMESTAMP NOT NULL,
    CHECK (principal_minor + interest_minor = amount_paid_minor)
);

-- Grain: one row per batch x entity x rule (latest evaluation of that rule for that batch).
CREATE TABLE IF NOT EXISTS fact_data_quality (
    batch_id        VARCHAR(40) NOT NULL,
    entity          VARCHAR(20) NOT NULL,
    rule_name       VARCHAR(80) NOT NULL,
    dimension       VARCHAR(24) NOT NULL,   -- completeness, validity, uniqueness, ...
    severity        VARCHAR(8) NOT NULL,    -- info, warning, critical
    failed_records  BIGINT NOT NULL,
    checked_records BIGINT NOT NULL,
    measured_value  DOUBLE PRECISION,       -- e.g. freshness lag in hours
    run_id          VARCHAR(40) NOT NULL,
    measured_at     TIMESTAMP NOT NULL,
    PRIMARY KEY (batch_id, entity, rule_name)
);

-- Grain: one row per pipeline step execution (every attempt is kept).
CREATE TABLE IF NOT EXISTS fact_pipeline_execution (
    execution_id  BIGINT PRIMARY KEY DEFAULT nextval('seq_execution_id'),
    run_id        VARCHAR(40) NOT NULL,
    batch_id      VARCHAR(40),
    pipeline      VARCHAR(20) NOT NULL,
    step          VARCHAR(30) NOT NULL,
    status        VARCHAR(10) NOT NULL CHECK (status IN ('SUCCESS', 'FAILED')),
    started_at    TIMESTAMP NOT NULL,
    finished_at   TIMESTAMP NOT NULL,
    duration_ms   BIGINT NOT NULL,
    records_in    BIGINT,
    records_out   BIGINT,
    error_message VARCHAR(500)
);

-- ------------------------------------------------------------ pipeline control

-- Grain: one row per batch; status is the furthest step that committed.
CREATE TABLE IF NOT EXISTS etl_batch (
    batch_id      VARCHAR(40) PRIMARY KEY,
    sequence      INTEGER NOT NULL,
    batch_type    VARCHAR(12) NOT NULL,
    business_date DATE NOT NULL,
    status        VARCHAR(16) NOT NULL,
    attempts      INTEGER NOT NULL,
    last_run_id   VARCHAR(40) NOT NULL,
    updated_at    TIMESTAMP NOT NULL
);

-- Grain: one high-water mark per pipeline x entity. Only advanced inside the
-- same transaction that commits the corresponding data.
CREATE TABLE IF NOT EXISTS etl_watermark (
    pipeline     VARCHAR(20) NOT NULL,
    entity       VARCHAR(30) NOT NULL,
    watermark_ts TIMESTAMP NOT NULL,
    batch_id     VARCHAR(40) NOT NULL,
    updated_at   TIMESTAMP NOT NULL,
    PRIMARY KEY (pipeline, entity)
);

-- Indexes for the most common analytical filters and joins.
CREATE INDEX IF NOT EXISTS ix_fact_transactions_date ON fact_transactions (date_key);
CREATE INDEX IF NOT EXISTS ix_fact_transactions_customer ON fact_transactions (customer_key);
CREATE INDEX IF NOT EXISTS ix_fact_loan_payments_due ON fact_loan_payments (due_date_key);
CREATE INDEX IF NOT EXISTS ix_dim_customer_id ON dim_customer (customer_id);
