"""Execute the educational SQL in ``sql/examples`` without side effects.

Each file runs inside a transaction that is always rolled back, so examples may
create indexes, views or temporary tables freely. Files named ``*.postgres.sql``
or ``*.duckdb.sql`` only run on that engine.
"""

from __future__ import annotations

import pandas as pd

from finflow.orchestration.pipeline import Runtime


class _Rollback(Exception):
    """Raised on purpose to discard everything an example did."""


def split_statements(sql: str) -> list[str]:
    # Examples never contain ';' inside string literals, so a simple split is safe.
    body = "\n".join(line for line in sql.splitlines() if not line.strip().startswith("--"))
    return [s.strip() for s in body.split(";") if s.strip()]


def run_examples(rt: Runtime, verbose: bool = False) -> dict[str, pd.DataFrame]:
    results: dict[str, pd.DataFrame] = {}
    for path in sorted((rt.settings.sql_dir / "examples").glob("*.sql")):
        parts = path.name.split(".")
        if len(parts) == 3 and parts[1] != rt.warehouse.dialect:
            continue
        statements = split_statements(path.read_text())
        try:
            with rt.warehouse.transaction():
                for statement in statements[:-1]:
                    rt.warehouse.execute(statement)
                results[path.stem] = rt.warehouse.query(statements[-1])
                raise _Rollback
        except _Rollback:
            pass
    return results
