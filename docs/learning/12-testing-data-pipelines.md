# 12 · Testing data pipelines

## Learning objectives
- Test transformations with small, explicit fixtures.
- Test contracts (schemas, dtypes) separately from logic.
- Write integration tests that assert pipeline guarantees (idempotency, reconciliation, recovery).

## Theory
Data pipeline bugs hide in three places: logic (wrong rule), contracts (a
column changes type), and behaviour across runs (duplicates, partial loads).
Each needs a different kind of test. Deterministic generators let integration
tests assert exact numbers.

## Where it is implemented
- `tests/unit/test_silver.py` — one parametrised case per rejection reason.
- `tests/contracts/` — source contracts and Silver dtypes.
- `tests/integration/test_lightweight_pipeline.py` — guarantees, including deliberate sabotage (`test_reconciliation_guard_catches_lost_rows`).
- `tests/integration/test_cli.py` — CLI smoke tests.
- `tests/integration/test_data_services.py` — isolated tests against real services.
- `docs/testing.md`.

## Reproduce
```bash
make test
uv run pytest tests/unit/test_silver.py -q -k "invalid_records"
make coverage
```

## Expected results
All tests pass (102 at the time of writing); coverage around 91%.

## Exercises
1. Write a test proving a transaction with currency `usd` (lower case) is accepted and normalised.
2. Write a property-based test (Hypothesis) for `parse_amount_minor`: any `Decimal` with ≤ 2 decimals round-trips through `format_minor`.
3. Break it: change `keep="first"` to `keep="last"` in the duplicate detection. Which tests catch it? If none, write one.
4. Add a test that the quality gate's threshold is read from config (set it to 0.01 and expect failure).

## Common mistakes
- Fixtures copied from production (privacy, size, non-determinism).
- Asserting only "no exception".
- Integration tests sharing state with the developer's data.

## Interview questions
1. How do you test a data pipeline?
2. Unit vs integration vs contract tests for data?
3. How do you test idempotency?
4. How do you keep integration tests fast and isolated?

Solutions: [solutions/12.md](solutions/12.md)
