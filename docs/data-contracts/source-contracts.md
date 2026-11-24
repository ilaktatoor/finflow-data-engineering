# Source data contracts

What each simulated operational system promises to send. The machine-readable
version is `src/finflow/validation/contracts.py`; this page was generated from it
and `tests/contracts/` verify the generator honours it.

All values arrive as text (CSV, JSON or JSONL; API and database rows are
serialised to JSONL in Bronze). Timestamps are ISO-8601 in UTC, amounts are
decimal strings with at most two decimals, rates at most six.

Breaking a contract never crashes the pipeline: the record is quarantined with
the reason, and the batch fails only if the reject rate crosses the quality gate.

## `exchange_rates`

- Format: `csv` file (`data/landing/<batch>/exchange_rates.csv`); source system `treasury_files` (lightweight) / `rates_api` (data profile)
- Natural key: `rate_key` (derived: `currency_code|rate_date`)
- Watermark / freshness column: `rate_date`

| Field | Required | Parsed as | Rule |
|---|---|---|---|
| `rate_date` | yes | date |  |
| `currency_code` | yes | text, upper-cased | one of `USD`, `EUR`, `CAD` |
| `rate_to_mxn` | yes | rate → `rate_to_mxn_micros` (Int64) | > 0 |

## `merchants`

- Format: `json` file (`data/landing/<batch>/merchants.json`); source system `merchant_files` (lightweight) / `merchant_api` (data profile)
- Natural key: `merchant_id`
- Watermark / freshness column: `updated_at`

| Field | Required | Parsed as | Rule |
|---|---|---|---|
| `merchant_id` | yes | text | matches `M\d{4}` |
| `merchant_name` | yes | text |  |
| `category` | yes | text, upper-cased |  |
| `updated_at` | yes | timestamp (UTC) |  |
| `city` | no | text |  |

## `customers`

- Format: `csv` file (`data/landing/<batch>/customers.csv`); source system `core_banking_files` (lightweight) / `core_banking_db` (data profile)
- Natural key: `customer_id`
- Watermark / freshness column: `updated_at`

| Field | Required | Parsed as | Rule |
|---|---|---|---|
| `customer_id` | yes | text | matches `C\d{5}` |
| `first_name` | yes | text |  |
| `last_name` | yes | text |  |
| `segment` | yes | text, upper-cased | one of `RETAIL`, `PREMIUM`, `SMB` |
| `created_at` | yes | timestamp (UTC) |  |
| `updated_at` | yes | timestamp (UTC) |  |
| `email` | no | text |  |
| `city` | no | text |  |
| `state` | no | text |  |

## `accounts`

- Format: `csv` file (`data/landing/<batch>/accounts.csv`); source system `core_banking_files` (lightweight) / `core_banking_db` (data profile)
- Natural key: `account_id`
- Watermark / freshness column: `updated_at`

| Field | Required | Parsed as | Rule |
|---|---|---|---|
| `account_id` | yes | text | matches `A\d{6}` |
| `customer_id` | yes | text | must exist in `customers` |
| `account_type` | yes | text, upper-cased | one of `CHECKING`, `SAVINGS` |
| `currency_code` | yes | text, upper-cased | one of `MXN`, `USD`, `EUR`, `CAD` |
| `status` | yes | text, upper-cased | one of `ACTIVE`, `CLOSED`, `FROZEN` |
| `opened_at` | yes | timestamp (UTC) |  |
| `updated_at` | yes | timestamp (UTC) |  |

## `cards`

- Format: `csv` file (`data/landing/<batch>/cards.csv`); source system `card_files` (lightweight) / `card_files` (data profile)
- Natural key: `card_id`
- Watermark / freshness column: `updated_at`

| Field | Required | Parsed as | Rule |
|---|---|---|---|
| `card_id` | yes | text | matches `K\d{6}` |
| `account_id` | yes | text | must exist in `accounts` |
| `network` | yes | text, upper-cased | one of `VISA`, `MASTERCARD` |
| `credit_limit` | yes | amount → `credit_limit_minor` (Int64 cents) | ≥ 0 |
| `status` | yes | text, upper-cased | one of `ACTIVE`, `BLOCKED`, `CANCELLED` |
| `issued_at` | yes | timestamp (UTC) |  |
| `updated_at` | yes | timestamp (UTC) |  |
| `card_last4` | no | text | matches `\d{4}` |

## `loans`

- Format: `csv` file (`data/landing/<batch>/loans.csv`); source system `lending_files` (lightweight) / `lending_db` (data profile)
- Natural key: `loan_id`
- Watermark / freshness column: `updated_at`

| Field | Required | Parsed as | Rule |
|---|---|---|---|
| `loan_id` | yes | text |  |
| `customer_id` | yes | text | must exist in `customers` |
| `account_id` | yes | text | must exist in `accounts` |
| `principal` | yes | amount → `principal_minor` (Int64 cents) | ≥ 0 |
| `annual_rate` | yes | rate → `annual_rate_micros` (Int64) | > 0 |
| `term_months` | yes | integer | > 0 |
| `currency_code` | yes | text, upper-cased | one of `MXN`, `USD`, `EUR`, `CAD` |
| `status` | yes | text, upper-cased | one of `ACTIVE`, `PAID_OFF`, `DEFAULT` |
| `disbursed_at` | yes | timestamp (UTC) |  |
| `updated_at` | yes | timestamp (UTC) |  |

Cross-field rules:

- The account must belong to `customer_id`.

## `loan_payments`

- Format: `csv` file (`data/landing/<batch>/loan_payments.csv`); source system `lending_files` (lightweight) / `lending_db` (data profile)
- Natural key: `payment_id`
- Watermark / freshness column: `updated_at`

| Field | Required | Parsed as | Rule |
|---|---|---|---|
| `payment_id` | yes | text |  |
| `loan_id` | yes | text | must exist in `loans` |
| `installment_number` | yes | integer | > 0 |
| `due_date` | yes | date |  |
| `amount` | yes | amount → `amount_minor` (Int64 cents) | ≥ 0 |
| `principal_component` | yes | amount → `principal_component_minor` (Int64 cents) | ≥ 0 |
| `interest_component` | yes | amount → `interest_component_minor` (Int64 cents) | ≥ 0 |
| `status` | yes | text, upper-cased | one of `ON_TIME`, `LATE`, `MISSED` |
| `updated_at` | yes | timestamp (UTC) |  |
| `paid_at` | no | timestamp (UTC) |  |

Cross-field rules:

- `principal_component + interest_component = amount` (exactly, in cents).
- Installments not `MISSED` require `paid_at`.

## `transactions`

- Format: `jsonl` file (`data/landing/<batch>/transactions.jsonl`); source system `transaction_files` (lightweight) / `transaction_files` (data profile)
- Natural key: `transaction_id`
- Watermark / freshness column: `event_ts`

| Field | Required | Parsed as | Rule |
|---|---|---|---|
| `transaction_id` | yes | text | matches `T[0-9A-Z]{9,12}` |
| `account_id` | yes | text | must exist in `accounts` |
| `customer_id` | yes | text | must exist in `customers` |
| `transaction_type` | yes | text, upper-cased | one of `PURCHASE`, `TRANSFER`, `WITHDRAWAL`, `DEPOSIT`, `FEE` |
| `amount` | yes | amount → `amount_minor` (Int64 cents) | > 0 |
| `currency_code` | yes | text, upper-cased | one of `MXN`, `USD`, `EUR`, `CAD` |
| `status` | yes | text, upper-cased | one of `COMPLETED`, `FAILED`, `PENDING`, `REVERSED` |
| `channel` | yes | text, upper-cased | one of `CARD_POS`, `ONLINE`, `ATM`, `BRANCH`, `MOBILE`, `SYSTEM` |
| `event_ts` | yes | timestamp (UTC) |  |
| `card_id` | no | text | must exist in `cards` |
| `merchant_id` | no | text | must exist in `merchants` |
| `counterparty_account_id` | no | text |  |

Cross-field rules:

- `transaction_type = TRANSFER` requires `counterparty_account_id`.
- `transaction_type = PURCHASE` requires `merchant_id`.
- The account must belong to `customer_id` (`owner_mismatch`).
- Non-MXN transactions need an exchange rate for the event date (`missing_exchange_rate`).

## Intentional contract violations

The generator corrupts `error_rate` (default 5%) of transaction records, spread
evenly over these types, and counts them in `_generation_report.json`:

| Injected error | Example | Expected handling |
|---|---|---|
| duplicate | exact re-send of a valid record | kept once; copy quarantined as `duplicate` |
| missing_required | `account_id: null` | rejected `missing:account_id` |
| invalid_currency | `XYZ`, `PESO`, `usd$` | rejected `currency_code:isin` |
| invalid_timestamp | `2026-13-45T25:61:00Z`, `31/01/2026 10:00` | rejected `invalid_format:event_ts` |
| malformed_amount | `12,34.5x`, `$100`, `1.2.3` | rejected `invalid_format:amount` |
| unknown_customer | `C99999` | rejected `unknown_ref:customer_id` (and `owner_mismatch`) |
| unknown_account | `A999999` | rejected `unknown_ref:account_id` |
| invalid_status | `DONE`, `completed!` | rejected `status:isin` |
| owner_mismatch | another customer's id | rejected `owner_mismatch` |
| schema_mismatch | field `amount` renamed to `txn_amount` | rejected `schema_mismatch` |

Incremental batches also contain **valid** edge cases: late-arriving
transactions (up to 7 days old) and status corrections of earlier
transactions. They are accepted, flagged and upserted, never rejected.
