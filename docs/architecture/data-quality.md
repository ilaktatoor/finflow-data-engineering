# Data quality

## Rules by dimension

| Dimension | Rule names (as stored in `fact_data_quality.rule_name`) | Implemented in |
|---|---|---|
| Completeness | `missing:<column>` | Pandera `nullable=False` |
| Validity | `schema_mismatch`, `invalid_format:<column>`, `<column>:isin`, `<column>:str_matches`, `<column>:greater_than` … | silver.py parsing + Pandera checks |
| Uniqueness | `duplicate` | silver.py (first valid occurrence wins) |
| Referential integrity | `unknown_ref:<column>` | silver.py, against keys in the lake |
| Consistency | `owner_mismatch`, `missing_exchange_rate`, `business:<rule>` | silver.py + Pandera dataframe checks |
| Freshness | `freshness_lag_hours` (transactions, exchange rates) | quality.py: batch window end − newest event |
| Reconciliation | `reconciliation` per entity; fact reconciliation in the load; ETL vs ELT | quality.py, pipeline.py, `sql/quality/` |

## Reconciliation, three times

1. **Per entity in Silver**: `input = accepted + rejected + duplicates`. A
   mismatch is a critical failure (it would mean a bug lost records).
2. **Per load**: every staged fact row must exist in the target with the same
   amount, and every transaction must point at the customer version valid at
   its event time (`pipeline._reconcile_facts`). The first catches joins that
   silently drop rows, the second joins that silently attach the wrong SCD2
   version — which counts and sums cannot see. Two integration tests sabotage
   the load SQL to prove each guard fires.
3. **ETL vs ELT**: two independent implementations must agree per day on
   count, failures and MXN value (`sql/quality/etl_elt_reconciliation.sql`).

## Thresholds (`config/finflow.toml`)

```toml
[quality]
max_reject_rate = 0.10          # critical: the batch is refused
warn_reject_rate = 0.02         # warning: logged and reported
max_freshness_lag_hours = 48
```

## The pipeline that fails on purpose

`make demo-quality-gate` generates a batch with 30% corrupted transactions.
Measured result: 540 of 2,060 records rejected (26.21%), the CLI exits with
code 2 and `QUALITY GATE FAILED: transactions: reject rate 26.21% exceeds the
critical threshold 10.00%`; nothing reaches Silver or the warehouse, while the
quality rows and the quarantine are kept for investigation.

## Where to look

- Per batch: `finflow quality-report [--batch ID]`, or
  `reports/quality/<batch_id>/report.json` in the lake.
- Over time: `mart_data_quality_rules`, `mart_batch_quality`.
- Individual records: `rejected/<entity>/batch_id=<id>.parquet`
  (`raw_record` has the original payload, `reasons` every failed rule).

## Measured on the default demo (small profile + 2 incremental days)

| Batch | Transactions in | Rejected | Duplicates | Reject rate |
|---|---|---|---|---|
| b000-historical | 2,010 | 90 | 10 | 4.48% (warning) |
| b001-2026-01-31 | 96 | 4 | 1 | 4.17% (warning) |
| b002-2026-02-01 | 97 | 4 | 1 | 4.12% (warning) |

Every reject matches an error the generator injected on purpose
(`_generation_report.json` in each landing batch); the tests assert the exact
numbers.
