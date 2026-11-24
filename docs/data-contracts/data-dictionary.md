# Data dictionary

Warehouse tables (`sql/warehouse/01_schema.sql`). Types are shown as DuckDB
reports them; PostgreSQL uses the same declared types. Generated from the
schema of a real run, with descriptions maintained by hand.

Conventions: `*_minor` = integer cents, `*_micros` = integer × 1,000,000,
`*_key` = surrogate key, `*_id` = natural key from a source system, all
timestamps UTC without time zone.

## Dimensions

### `dim_date`

| Column | Type | Nullable | Description |
|---|---|---|---|
| `date_key` | INTEGER | no | Date as integer YYYYMMDD (FK to dim_date) |
| `full_date` | DATE | no | Calendar date |
| `year` | SMALLINT | no | Calendar year |
| `quarter` | SMALLINT | no | 1–4 |
| `month` | SMALLINT | no | 1–12 |
| `month_name` | VARCHAR | no | English month name |
| `day_of_month` | SMALLINT | no | 1–31 |
| `iso_day_of_week` | SMALLINT | no | 1 = Monday … 7 = Sunday |
| `is_weekend` | BOOLEAN | no | Saturday or Sunday |

### `dim_currency`

| Column | Type | Nullable | Description |
|---|---|---|---|
| `currency_key` | SMALLINT | no | Surrogate key |
| `currency_code` | VARCHAR | no | ISO 4217 code |
| `currency_name` | VARCHAR | no | Display name |
| `minor_unit` | SMALLINT | no | Decimal places of the currency |

### `dim_transaction_type`

| Column | Type | Nullable | Description |
|---|---|---|---|
| `transaction_type_key` | SMALLINT | no | Surrogate key |
| `code` | VARCHAR | no | Business code |
| `description` | VARCHAR | no | Human description |
| `direction` | VARCHAR | no | DEBIT or CREDIT from the customer's view |

### `dim_customer`

| Column | Type | Nullable | Description |
|---|---|---|---|
| `customer_key` | BIGINT | no | Surrogate key of one customer *version* |
| `customer_id` | VARCHAR | no | Natural key from core banking |
| `first_name` | VARCHAR | no | Synthetic first name |
| `last_name` | VARCHAR | no | Synthetic last name |
| `email` | VARCHAR | yes | Synthetic address on example.test |
| `city` | VARCHAR | yes | City (Faker es_MX) |
| `state` | VARCHAR | yes | State (Faker es_MX) |
| `segment` | VARCHAR | no | RETAIL, PREMIUM or SMB (SCD2-tracked) |
| `customer_since` | TIMESTAMP | no | Customer creation timestamp |
| `attributes_hash` | VARCHAR | no | Hash of the tracked attributes, used to detect changes |
| `valid_from` | TIMESTAMP | no | Version start (inclusive); first version starts 1900-01-01 |
| `valid_to` | TIMESTAMP | yes | Version end (exclusive); NULL while current |
| `is_current` | BOOLEAN | no | TRUE for the latest version |
| `batch_id` | VARCHAR | no | Batch that last wrote the row (lineage) |

### `dim_account`

| Column | Type | Nullable | Description |
|---|---|---|---|
| `account_key` | BIGINT | no | Surrogate key |
| `account_id` | VARCHAR | no | Natural key |
| `customer_id` | VARCHAR | no | Natural key from core banking |
| `account_type` | VARCHAR | no | CHECKING or SAVINGS |
| `currency_code` | VARCHAR | no | ISO 4217 code |
| `status` | VARCHAR | no | Business status |
| `opened_at` | TIMESTAMP | no | Account opening timestamp |
| `updated_at` | TIMESTAMP | no | Last change in the source system |
| `batch_id` | VARCHAR | no | Batch that last wrote the row (lineage) |

### `dim_card`

| Column | Type | Nullable | Description |
|---|---|---|---|
| `card_key` | BIGINT | no | Surrogate key |
| `card_id` | VARCHAR | no | Natural key (never a card number) |
| `account_id` | VARCHAR | no | Natural key |
| `network` | VARCHAR | no | VISA or MASTERCARD |
| `card_last4` | VARCHAR | yes | 4 random digits (synthetic) |
| `credit_limit_minor` | BIGINT | no | Limit in cents |
| `status` | VARCHAR | no | Business status |
| `issued_at` | TIMESTAMP | no | Issue timestamp |
| `updated_at` | TIMESTAMP | no | Last change in the source system |
| `batch_id` | VARCHAR | no | Batch that last wrote the row (lineage) |

### `dim_merchant`

| Column | Type | Nullable | Description |
|---|---|---|---|
| `merchant_key` | BIGINT | no | Surrogate key |
| `merchant_id` | VARCHAR | no | Natural key |
| `merchant_name` | VARCHAR | no | Synthetic company name |
| `category` | VARCHAR | no | Merchant category |
| `city` | VARCHAR | yes | City (Faker es_MX) |
| `updated_at` | TIMESTAMP | no | Last change in the source system |
| `batch_id` | VARCHAR | no | Batch that last wrote the row (lineage) |

### `dim_loan`

| Column | Type | Nullable | Description |
|---|---|---|---|
| `loan_key` | BIGINT | no | Surrogate key |
| `loan_id` | VARCHAR | no | Natural key |
| `customer_id` | VARCHAR | no | Natural key from core banking |
| `account_id` | VARCHAR | no | Natural key |
| `principal_minor` | BIGINT | no | Principal in cents |
| `annual_rate_micros` | BIGINT | no | Annual interest rate × 1,000,000 (e.g. 0.245 → 245000) |
| `term_months` | SMALLINT | no | 12, 24 or 36 |
| `currency_code` | VARCHAR | no | ISO 4217 code |
| `status` | VARCHAR | no | Business status |
| `disbursed_at` | TIMESTAMP | no | Disbursement timestamp |
| `updated_at` | TIMESTAMP | no | Last change in the source system |
| `batch_id` | VARCHAR | no | Batch that last wrote the row (lineage) |

### `ref_exchange_rate`

| Column | Type | Nullable | Description |
|---|---|---|---|
| `currency_code` | VARCHAR | no | ISO 4217 code |
| `rate_date` | DATE | no | Day the rate applies to |
| `rate_micros` | BIGINT | no | Units of MXN per unit of currency × 1,000,000 |
| `batch_id` | VARCHAR | no | Batch that last wrote the row (lineage) |

## Facts

### `fact_transactions`

| Column | Type | Nullable | Description |
|---|---|---|---|
| `transaction_id` | VARCHAR | no | Natural key from the transaction system |
| `date_key` | INTEGER | no | Date as integer YYYYMMDD (FK to dim_date) |
| `customer_key` | BIGINT | no | Surrogate key of one customer *version* |
| `account_key` | BIGINT | no | Surrogate key |
| `card_key` | BIGINT | yes | Surrogate key |
| `merchant_key` | BIGINT | yes | Surrogate key |
| `transaction_type_key` | SMALLINT | no | Surrogate key |
| `currency_key` | SMALLINT | no | Surrogate key |
| `counterparty_account_id` | VARCHAR | yes | Receiving account of a TRANSFER |
| `amount_minor` | BIGINT | no | Amount in the transaction currency, cents |
| `amount_mxn_minor` | BIGINT | no | Amount converted to MXN, cents (integer half-up rounding) |
| `rate_micros` | BIGINT | no | Units of MXN per unit of currency × 1,000,000 |
| `status` | VARCHAR | no | Business status |
| `channel` | VARCHAR | no | CARD_POS, ONLINE, ATM, BRANCH, MOBILE or SYSTEM |
| `event_ts` | TIMESTAMP | no | When the transaction happened (UTC) |
| `is_late_arriving` | BOOLEAN | no | Event happened before the window of the batch that delivered it |
| `is_risk_flagged` | BOOLEAN | no | Matched at least one SIMULATED risk rule (not a fraud model) |
| `risk_reasons` | VARCHAR | yes | HIGH_AMOUNT | VELOCITY | FOREIGN_NIGHT |
| `batch_id` | VARCHAR | no | Batch that last wrote the row (lineage) |
| `loaded_at` | TIMESTAMP | no | When the row was written to the warehouse (UTC) |

### `fact_loan_payments`

| Column | Type | Nullable | Description |
|---|---|---|---|
| `payment_id` | VARCHAR | no | Natural key of the installment |
| `loan_key` | BIGINT | no | Surrogate key |
| `customer_key` | BIGINT | no | Surrogate key of one customer *version* |
| `due_date_key` | INTEGER | no | Due date (FK dim_date) |
| `paid_date_key` | INTEGER | yes | Payment date (FK dim_date); NULL if missed |
| `installment_number` | SMALLINT | no | 1-based installment |
| `amount_paid_minor` | BIGINT | no | Paid amount, cents (0 if missed) |
| `principal_minor` | BIGINT | no | Principal in cents |
| `interest_minor` | BIGINT | no | Interest component, cents |
| `status` | VARCHAR | no | Business status |
| `days_late` | INTEGER | yes | Days between due date and payment; NULL if missed |
| `batch_id` | VARCHAR | no | Batch that last wrote the row (lineage) |
| `loaded_at` | TIMESTAMP | no | When the row was written to the warehouse (UTC) |

### `fact_data_quality`

| Column | Type | Nullable | Description |
|---|---|---|---|
| `batch_id` | VARCHAR | no | Batch that last wrote the row (lineage) |
| `entity` | VARCHAR | no | Source entity |
| `rule_name` | VARCHAR | no | Rule identifier (see data-quality.md) |
| `dimension` | VARCHAR | no | Quality dimension |
| `severity` | VARCHAR | no | info, warning or critical |
| `failed_records` | BIGINT | no | Records failing the rule |
| `checked_records` | BIGINT | no | Records evaluated |
| `measured_value` | DOUBLE | yes | Rule-specific measurement (reject rate, freshness lag in hours) |
| `run_id` | VARCHAR | no | Pipeline run identifier |
| `measured_at` | TIMESTAMP | no | Evaluation time |

### `fact_pipeline_execution`

| Column | Type | Nullable | Description |
|---|---|---|---|
| `execution_id` | BIGINT | no | Surrogate key |
| `run_id` | VARCHAR | no | Pipeline run identifier |
| `batch_id` | VARCHAR | yes | Batch that last wrote the row (lineage) |
| `pipeline` | VARCHAR | no | etl or elt |
| `step` | VARCHAR | no | Step name |
| `status` | VARCHAR | no | Business status |
| `started_at` | TIMESTAMP | no | Step start |
| `finished_at` | TIMESTAMP | no | Step end |
| `duration_ms` | BIGINT | no | Wall-clock duration |
| `records_in` | BIGINT | yes | Records read |
| `records_out` | BIGINT | yes | Records written / accepted |
| `error_message` | VARCHAR | yes | Exception type and message, truncated to 500 chars |

## Pipeline control

### `etl_batch`

| Column | Type | Nullable | Description |
|---|---|---|---|
| `batch_id` | VARCHAR | no | Batch that last wrote the row (lineage) |
| `sequence` | INTEGER | no | Processing order |
| `batch_type` | VARCHAR | no | historical or incremental |
| `business_date` | DATE | no | Business day of the batch |
| `status` | VARCHAR | no | Business status |
| `attempts` | INTEGER | no | Number of runs that touched the batch |
| `last_run_id` | VARCHAR | no | Most recent run |
| `updated_at` | TIMESTAMP | no | Last change in the source system |

### `etl_watermark`

| Column | Type | Nullable | Description |
|---|---|---|---|
| `pipeline` | VARCHAR | no | etl or elt |
| `entity` | VARCHAR | no | Source entity |
| `watermark_ts` | TIMESTAMP | no | High-water mark: end of the last committed extraction window |
| `batch_id` | VARCHAR | no | Batch that last wrote the row (lineage) |
| `updated_at` | TIMESTAMP | no | Last change in the source system |

## ELT and marts

`stg_raw_transactions`, `elt_transactions`, `elt_rejected_transactions` and
`elt_watermark` are documented in `sql/staging/00_staging_schema.sql`; every
mart's columns and purpose in `sql/marts/*.sql` and
[data-model.md](../architecture/data-model.md#data-marts-sqlmarts).
