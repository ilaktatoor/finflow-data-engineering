# Contributing

This is primarily a personal learning project, but improvements are welcome.

## Workflow

```bash
make setup        # dependencies, .env, pre-commit hooks
make check        # ruff, mypy, tests — what CI runs
```

- Branch from `main`; one logical change per pull request.
- Conventional Commits (`feat:`, `fix:`, `docs:`, `test:`, `refactor:`, `ci:`, `chore:`).
- Add or update tests with every behaviour change. Prefer assertions on the
  generator's expected numbers over hard-coded counts.
- Keep warehouse SQL portable between DuckDB and PostgreSQL; put engine-specific
  statements in a `*.postgres.sql` / `*.duckdb.sql` sibling and say why.
- Never use floats for money (see ADR 0007).
- Update the docs that describe what you changed, and
  `docs/implementation-status.md` if a component's verification status changes.

## Adding a source entity (checklist)

1. Contract in `src/finflow/validation/contracts.py` (+ position in `PROCESSING_ORDER`).
2. Generator output and `FILE_FORMATS` entry.
3. Silver dtype expectations in `tests/contracts/test_silver_contracts.py`.
4. Warehouse table in `sql/warehouse/01_schema.sql` and a load script in `LOAD_SCRIPTS`.
5. Docs: `docs/data-contracts/`, data dictionary.
