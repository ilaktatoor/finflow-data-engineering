# 13 · Performance optimisation

## Learning objectives
- Measure before optimising; report medians with context.
- Know which optimisations matter at which scale.

## Theory
Cost = fixed overhead + per-row work. At small scale the fixed part dominates,
so many "optimisations" are invisible or negative. Vectorisation removes
per-row interpreter overhead and wins at every scale; I/O format, chunking and
indexes win when data is large relative to overhead and memory.

## Where it is implemented
- `src/finflow/analytics/benchmarks.py` — six comparisons, each asserting both implementations agree before timing.
- `docs/performance.md` — measured results and their interpretation.
- `sql/examples/17_indexes_and_explain.sql`.
- `notebooks/03_pandas_performance.ipynb`.

## Reproduce
```bash
make benchmark && cat data/reports/benchmarks.json
```

## Expected results (shape, not exact numbers)
Vectorised conversion ~two orders of magnitude faster than `iterrows`;
categoricals ~50× smaller; Parquet ~6× smaller than CSV but not faster to read
at 2k rows; chunking and indexes roughly neutral at this size.

## Exercises
1. Generate the large profile in a separate data dir and rerun the benchmarks. Which results change shape?
2. Add a benchmark: DuckDB vs Pandas for the daily aggregate on Silver.
3. On PostgreSQL (data profile), run `EXPLAIN ANALYZE` for `10_lag_lead.sql` with and without `ix_fact_transactions_account_ts`. Does the sort disappear?
4. Break it: remove the correctness assertion from `bench_vectorized_vs_loop` and introduce a rounding bug in the loop. Why is "fast but wrong" the worst outcome?

## Common mistakes
- Timing a single run; including import time; comparing different results.
- Optimising code that is 1% of the wall time.
- Extrapolating small benchmarks to production.

## Interview questions
1. How do you find the bottleneck in a slow pipeline?
2. When does Parquet beat CSV, and when does it not?
3. When is an index useless or harmful?
4. How do you reduce Pandas memory usage?

Solutions: [solutions/13.md](solutions/13.md)
