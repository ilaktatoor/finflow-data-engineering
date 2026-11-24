# ETL design

The ETL path transforms data **before** it reaches the warehouse: Pandas and
Pandera type, validate, deduplicate, conform and enrich every record, and only
clean, conformed rows are loaded. Code: `src/finflow/orchestration/pipeline.py`.

## Steps

| Step | Function | Reads | Writes | Idempotency |
|---|---|---|---|---|
| ingest | `pipeline.ingest` | source adapters | Bronze objects + batch marker | batch marker present → no extraction; identical bytes → no-op; different bytes → `BronzeConflictError` |
| validate | `pipeline.validate` | Bronze | quality report, rejected | re-running overwrites the same report |
| transform | `pipeline.transform` | Bronze + earlier Silver (reference keys) | Silver, rejected, quality report | the batch's Silver files are deleted and rewritten |
| load | `pipeline.load` | Silver of the batch | warehouse, in **one** transaction | upserts on natural keys; quality rows replaced per batch |

`pipeline.run_etl` runs the three main steps, records each attempt in
`fact_pipeline_execution`, and moves `etl_batch.status` through
`INGESTED → TRANSFORMED → LOADED` (or `FAILED` / `QUALITY_FAILED`).
`pipeline.run_pending` processes landing batches in `sequence` order and skips
batches already `LOADED`; `--force` reprocesses them.

## Transform internals (`src/finflow/transformations/silver.py`)

Each record collects every reason it fails, in five stages:

1. **Schema**: required keys present in the payload → `schema_mismatch`.
2. **Parsing** (vectorised): ISO-8601 timestamps, dates, amounts → integer minor
   units, rates → integer micros, integers → `invalid_format:<column>`.
3. **Pandera** (`validation/contracts.py`): required values, domains
   (`isin`), patterns, ranges and cross-field business rules
   (`transfer_requires_counterparty`, `purchase_requires_merchant`,
   `payment_components_reconcile`, `paid_installment_requires_paid_at`).
4. **Uniqueness**: the first valid occurrence of a natural key wins; later ones
   are `duplicate` (not rejected).
5. **References**: foreign keys must exist in Silver (earlier batches) or in
   this batch; transactions must belong to the account's owner
   (`owner_mismatch`); foreign-currency transactions need a rate
   (`missing_exchange_rate`).

Accepted transactions are then enriched: `amount_mxn_minor` (exact integer
conversion), `is_late_arriving` (event before the batch window) and the
simulated risk flags (`transformations/risk.py`).

Entities are processed dimensions-first (`PROCESSING_ORDER`), so a
transaction can reference an account that arrives in the same batch.

## Quality gate

`validation/quality.py` turns the results into rows for `fact_data_quality`
and decides:

- reject rate > `quality.max_reject_rate` (10%) for any entity → **critical**:
  `QualityGateError`, exit code 2, nothing is written to Silver or the warehouse,
  but the quality report and the quarantine *are* written, so the failure can
  be investigated.
- reject rate > `quality.warn_reject_rate` (2%) → warning, the batch loads.
- an entity whose counts do not reconcile → critical (this would be a bug).

Thresholds live in `config/finflow.toml`.

## Load internals

Inside one database transaction:

1. Stage each Silver frame into `stg_<entity>`.
2. Run `sql/warehouse/1x_load_*.sql` (dimensions) and `2x_load_fact_*.sql` (facts).
3. **Reconcile**: every staged fact row must be in the target with the same
   total amount, and attached to the customer version valid at its event time;
   otherwise `ReconciliationError`.
4. Replace this batch's rows in `fact_data_quality`.
5. Advance `etl_watermark` for every extracted entity to the batch window end.
6. Commit. A failure anywhere (including `FINFLOW_FAIL_AT=load`) rolls back
   all of it: no partial loads, no advanced watermark.

## Upsert semantics

Facts upsert on their natural key with a batch guard:

```sql
ON CONFLICT (transaction_id) DO UPDATE SET ... WHERE EXCLUDED.batch_id >= fact_transactions.batch_id
```

A later batch can correct a transaction (the generator re-sends a few PENDING
transactions as COMPLETED); replaying an older batch cannot undo the
correction. SCD1 dimensions use the same idea with `updated_at`.

## Why ETL here

Validation is rich (cross-field rules, references across batches, exact money
parsing) and the rejected records need their original payload and every
reason. That is easier to express, test and explain in Python than in SQL.
See [elt-design.md](elt-design.md) for the contrast.
