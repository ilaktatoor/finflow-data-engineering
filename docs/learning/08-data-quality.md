# 08 · Data quality

## Learning objectives
- Express rules as data contracts and Pandera schemas.
- Quarantine invalid records without losing them; measure quality per rule.
- Gate a pipeline on thresholds; reconcile counts and amounts.

## Theory
Quality dimensions: completeness, validity, uniqueness, consistency,
referential integrity, timeliness/freshness, and accuracy (which needs an
external truth and is out of scope). Record-level rules quarantine; batch-level
thresholds decide whether the batch is fit to load.

## Where it is implemented
- `src/finflow/validation/contracts.py` — `EntityContract`, `CONTRACTS`, `pandera_schema`, `_business_checks`.
- `src/finflow/transformations/silver.py` — staged validation, `_pandera_reasons`, quarantine.
- `src/finflow/validation/quality.py` — `evaluate`, `rule_dimension`, thresholds.
- `config/finflow.toml` → `[quality]`.
- `sql/marts/60_mart_data_quality.sql`, `finflow quality-report`.
- `docs/architecture/data-quality.md`, `docs/data-contracts/source-contracts.md`.

## Reproduce
```bash
uv run finflow quality-report
make demo-quality-gate
uv run python -c "
import pandas as pd
q = pd.read_parquet('data/lake/rejected/transactions')
print(q[['natural_key','disposition','reasons']].head(12))"
```

## Expected results
- Historical batch: 90 rejected of 2,010 (4.48%, warning), 10 duplicates.
- Quality gate demo: 26.21% rejected, exit code 2, `QUALITY_FAILED`.

## Exercises
1. Add a rule: `amount` for `FEE` must be ≤ 500.00 MXN. Add a test that fails before your change.
2. Make the gate per rule: fail if `schema_mismatch` affects more than 1% of records, regardless of the total.
3. Break it: set `ignore_na=False` back to the default in `_business_checks` and run `pytest tests/unit/test_silver.py`. Which tests fail and why? (This was a real bug found while building FinFlow.)
4. Add a freshness gate: fail the batch if `freshness_lag_hours` exceeds the threshold.

## Common mistakes
- Dropping invalid rows (silent loss) or failing on the first one (fragile).
- Reporting only pass/fail without counts per rule.
- Measuring quality after loading instead of before.

## Interview questions
1. Name the data quality dimensions and give a rule for each.
2. Quarantine vs reject vs fail the batch — how do you decide?
3. How would you detect a schema change from a producer?
4. What is a data contract?

Solutions: [solutions/08.md](solutions/08.md)
