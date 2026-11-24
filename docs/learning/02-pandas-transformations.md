# 02 · Pandas transformations

## Learning objectives
- Ingest CSV/JSON into typed DataFrames with nullable dtypes.
- Parse, validate and enrich data with vectorised operations.
- Use merges, groupby, time-based rolling windows and Parquet serialisation.
- Recognise when row-by-row code is the bottleneck.

## Theory
A DataFrame is a set of typed columns. Pandas is fast when an operation runs
once per column in compiled code (vectorised) and slow when Python runs once
per row (`iterrows`, `apply(axis=1)`). Pandas 3 defaults to Arrow-backed
strings and copy-on-write; nullable `Int64`, `boolean` and `string` dtypes
represent missing values as `<NA>` without converting integers to float.

## Why it matters
Most batch transformations at small-to-medium scale are Pandas or something
with the same mental model (Polars, Spark DataFrames). Getting dtypes right is
what keeps money exact and joins correct.

## Where it is implemented

| Concept | File → function |
|---|---|
| Records → string DataFrame | `transformations/silver.py` → `transform_entity` (step 1) |
| Timestamp parsing with error capture | `silver.py` → `_to_naive_utc` (`errors="coerce"`, then "raw not null but parsed null") |
| Exact decimal parsing without float | `common/money.py` → `_parse_fixed_point` (string split, `Int64`) |
| Vectorised integer arithmetic | `common/money.py` → `convert_minor` |
| Duplicate detection | `silver.py` → `key.where(valid).duplicated(keep="first")` |
| Merge (left join) | `silver.py` → `_attach_rates` |
| Boolean filtering, masks | throughout `transform_entity` |
| Time-based rolling window per group | `transformations/risk.py` → `flag_transactions` (`groupby().rolling("10min", on=...)`) |
| Hashing rows for change detection | `silver.py` → `_finalize` (`pd.util.hash_pandas_object`) |
| GroupBy + Parquet partitioning | `orchestration/pipeline.py` → `_write_silver` |
| SQL ingestion into Pandas | `warehouse/base.py` → `PostgresWarehouse.query` (`pd.read_sql`) |
| Chunked reading | `analytics/benchmarks.py` → `bench_chunked` |
| Memory optimisation | `analytics/benchmarks.py` → `bench_memory_dtypes` |
| Pivot tables | notebook `03_pandas_performance.ipynb` exercise; see solution |

## How it works: one rejection, step by step
For the record `{"amount": "12,34.5x", ...}`:
1. `parse_amount_minor` applies `str.fullmatch` with the amount regex → no match → `<NA>`.
2. `failed = values.notna() & typed[...].isna()` is `True` → reason `invalid_format:amount`.
3. Pandera's not-null check on `amount_minor` also fails, but `_pandera_reasons`
   skips it because the null came from a failed parse.
4. The record is excluded from `accepted` and written to the quarantine with its raw JSON.

## Reproduce
```bash
uv run python -c "
import pandas as pd
from finflow.common.money import parse_amount_minor, convert_minor
s = parse_amount_minor(pd.Series(['100.5', '12,34.5x', '0.10']))
print(s.tolist(), s.dtype)
print(convert_minor(pd.Series([1000], dtype='Int64'), pd.Series([17_250_000], dtype='Int64')).tolist())
"
uv run pytest tests/unit/test_silver.py -q
```

## Expected results
`[10050, <NA>, 10]` with dtype `Int64`, then `[17250]`; all `test_silver.py` tests pass.

## Exercises
1. Write `bench_apply` in `benchmarks.py` timing `df.apply(axis=1)` for the conversion. Where does it land relative to `iterrows` and the vectorised version?
2. Build a pivot table: rows = `txn_date`, columns = `status`, values = count, from Silver transactions.
3. Break it: change `_to_naive_utc` to use `errors="raise"`. What happens to the batch, and why is coercing + recording the right choice?
4. Add a new rule: transactions with `channel = 'ATM'` must be `WITHDRAWAL` or `DEPOSIT`. Add it as a Pandera dataframe check and a test.

## Suggested modifications
- Replace the Faker-based `city` with a categorical dtype in Silver and measure the Parquet size change.
- Process the medium profile in chunks of 1,000 records per entity and compare results.

## Common mistakes
- `astype(float)` on money.
- Merging without checking key uniqueness (row explosion). `_attach_rates` relies on one rate per currency and day.
- `df[df.x > 0]["y"] = ...` chained assignment (no effect under copy-on-write).
- Forgetting that `groupby().rolling(on=...)` in pandas 3 returns an index of
  `(group, on-column)`; `risk.py` documents how it maps results back.

## Interview questions
1. Why is `iterrows` slow, and what do you do instead?
2. How do you represent missing integers without turning the column into float?
3. A merge returns more rows than the left table. What happened?
4. How would you process a 50 GB CSV with Pandas on a 16 GB machine?

Solutions: [solutions/02.md](solutions/02.md)
