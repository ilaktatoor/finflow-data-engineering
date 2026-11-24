-- Operational database of the fictional bank (core banking + lending).
-- This is the *source* system the pipeline extracts from, not the warehouse.
-- Every table carries updated_at, maintained by the applications, which the
-- pipeline uses as its incremental extraction watermark.

CREATE TABLE IF NOT EXISTS customers (
    customer_id VARCHAR(10) PRIMARY KEY,
    first_name  VARCHAR(80) NOT NULL,
    last_name   VARCHAR(80) NOT NULL,
    email       VARCHAR(120),
    city        VARCHAR(80),
    state       VARCHAR(80),
    segment     VARCHAR(10) NOT NULL,
    created_at  TIMESTAMP NOT NULL,
    updated_at  TIMESTAMP NOT NULL
);

CREATE TABLE IF NOT EXISTS accounts (
    account_id    VARCHAR(10) PRIMARY KEY,
    customer_id   VARCHAR(10) NOT NULL REFERENCES customers (customer_id),
    account_type  VARCHAR(10) NOT NULL,
    currency_code VARCHAR(3) NOT NULL,
    status        VARCHAR(10) NOT NULL,
    opened_at     TIMESTAMP NOT NULL,
    updated_at    TIMESTAMP NOT NULL
);

CREATE TABLE IF NOT EXISTS loans (
    loan_id       VARCHAR(10) PRIMARY KEY,
    customer_id   VARCHAR(10) NOT NULL REFERENCES customers (customer_id),
    account_id    VARCHAR(10) NOT NULL REFERENCES accounts (account_id),
    principal     NUMERIC(14, 2) NOT NULL,
    annual_rate   NUMERIC(6, 4) NOT NULL,
    term_months   SMALLINT NOT NULL,
    currency_code VARCHAR(3) NOT NULL,
    status        VARCHAR(10) NOT NULL,
    disbursed_at  TIMESTAMP NOT NULL,
    updated_at    TIMESTAMP NOT NULL
);

CREATE TABLE IF NOT EXISTS loan_payments (
    payment_id          VARCHAR(12) PRIMARY KEY,
    loan_id             VARCHAR(10) NOT NULL REFERENCES loans (loan_id),
    installment_number  SMALLINT NOT NULL,
    due_date            DATE NOT NULL,
    paid_at             TIMESTAMP,
    amount              NUMERIC(14, 2) NOT NULL,
    principal_component NUMERIC(14, 2) NOT NULL,
    interest_component  NUMERIC(14, 2) NOT NULL,
    status              VARCHAR(8) NOT NULL,
    updated_at          TIMESTAMP NOT NULL
);

-- Incremental extraction filters on updated_at; index it.
CREATE INDEX IF NOT EXISTS ix_customers_updated_at ON customers (updated_at);
CREATE INDEX IF NOT EXISTS ix_accounts_updated_at ON accounts (updated_at);
CREATE INDEX IF NOT EXISTS ix_loans_updated_at ON loans (updated_at);
CREATE INDEX IF NOT EXISTS ix_loan_payments_updated_at ON loan_payments (updated_at);

-- Which landing batches the simulator has already written (seed bookkeeping).
CREATE TABLE IF NOT EXISTS seeded_batches (
    batch_id  VARCHAR(40) PRIMARY KEY,
    seeded_at TIMESTAMP NOT NULL
);
