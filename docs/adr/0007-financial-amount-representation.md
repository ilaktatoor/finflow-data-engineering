# 0007 — Integer minor units for money

Status: Accepted

## Context
Binary floating point cannot represent most decimal amounts (`0.1 + 0.2 != 0.3`).
Financial totals must reconcile to the cent.

## Decision
- Amounts are parsed from text straight into **integer minor units** (`Int64`
  cents) with string operations, never through `float`
  (`finflow.common.money.parse_amount_minor`).
- Exchange rates are **integer micros** (rate × 1,000,000).
- Conversion is integer arithmetic with half-away-from-zero rounding:
  `(amount * rate + 500_000) // 1_000_000` for positive amounts.
- The warehouse stores `BIGINT`; SQL uses integer division (DuckDB configured
  to match PostgreSQL). `NUMERIC` appears only in the operational source schema
  and for display (`/ 100.0`).

## Alternatives
- *`Decimal` objects in Pandas*: exact but object dtype, row-by-row speed
  (measured 77× slower than the integer version on the demo data).
- *`NUMERIC(18,2)` everywhere*: exact in SQL, but Pandas would still need a
  representation, and DuckDB/PostgreSQL decimal division rules differ.
- *float64*: fast and wrong.

## Consequences
- Totals reconcile exactly between ETL and ELT, across engines.
- Every amount column ends in `_minor` or `_micros`; a contract test fails if
  one is ever not `Int64`.
- `Int64` overflow is not a risk at these magnitudes (documented in `convert_minor`).

## Trade-offs
All currencies here have 2 decimals; currencies with 0 or 3 (JPY, KWD) would
need `dim_currency.minor_unit` to drive parsing, which is noted in the roadmap.
