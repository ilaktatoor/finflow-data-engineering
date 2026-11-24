"""Warehouse adapters: DuckDB (lightweight) and PostgreSQL (data mode).

Both expose the same five operations, which is all the pipeline needs. SQL files
in ``sql/warehouse`` are written in the subset both engines understand; the few
engine-specific statements live in ``*.postgres.sql`` / ``*.duckdb.sql`` files.
Bind parameters are always written as ``:name``.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Protocol

import duckdb
import pandas as pd
import sqlalchemy as sa

_PARAM = re.compile(r"(?<![:\w]):(\w+)")


class Warehouse(Protocol):
    dialect: str

    def execute(self, sql: str, params: dict[str, Any] | None = None) -> None: ...
    def query(self, sql: str, params: dict[str, Any] | None = None) -> pd.DataFrame: ...
    def stage(self, table: str, df: pd.DataFrame) -> None: ...
    def transaction(self) -> Any: ...
    def close(self) -> None: ...


class DuckDBWarehouse:
    dialect = "duckdb"

    def __init__(self, path: Path | str) -> None:
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.con = duckdb.connect(str(path))
        # PostgreSQL semantics for `/` on integers (7 / 2 = 3). Without it DuckDB
        # returns a DOUBLE, and money arithmetic would silently go through floats.
        self.con.execute("SET integer_division = true")

    @staticmethod
    def _convert(sql: str) -> str:
        return _PARAM.sub(r"$\1", sql)

    def execute(self, sql: str, params: dict[str, Any] | None = None) -> None:
        if params:
            self.con.execute(self._convert(sql), params)
        else:
            self.con.execute(sql)

    def query(self, sql: str, params: dict[str, Any] | None = None) -> pd.DataFrame:
        relation = self.con.execute(self._convert(sql), params) if params else self.con.execute(sql)
        return relation.df()

    def stage(self, table: str, df: pd.DataFrame) -> None:
        self.con.register("_staging_frame", df)
        try:
            self.con.execute(f"CREATE OR REPLACE TABLE {table} AS SELECT * FROM _staging_frame")
        finally:
            self.con.unregister("_staging_frame")

    @contextmanager
    def transaction(self) -> Iterator[DuckDBWarehouse]:
        self.con.begin()
        try:
            yield self
        except BaseException:
            self.con.rollback()
            raise
        self.con.commit()

    def close(self) -> None:
        self.con.close()


class PostgresWarehouse:
    dialect = "postgres"

    def __init__(self, url: str) -> None:
        self.engine = sa.create_engine(url, pool_pre_ping=True)
        self._conn: sa.Connection | None = None

    @contextmanager
    def _connection(self) -> Iterator[sa.Connection]:
        if self._conn is not None:  # inside transaction(): reuse it
            yield self._conn
        else:
            with self.engine.begin() as conn:  # autocommit-per-statement outside a transaction
                yield conn

    def execute(self, sql: str, params: dict[str, Any] | None = None) -> None:
        with self._connection() as conn:
            if params:
                conn.execute(sa.text(sql), params)
            else:
                conn.exec_driver_sql(sql)

    def query(self, sql: str, params: dict[str, Any] | None = None) -> pd.DataFrame:
        with self._connection() as conn:
            return pd.read_sql(sa.text(sql), conn, params=params or {})

    def stage(self, table: str, df: pd.DataFrame) -> None:
        with self._connection() as conn:
            df.to_sql(table, conn, if_exists="replace", index=False, method="multi", chunksize=1000)

    @contextmanager
    def transaction(self) -> Iterator[PostgresWarehouse]:
        with self.engine.connect() as conn, conn.begin():
            self._conn = conn
            try:
                yield self
            finally:
                self._conn = None

    def close(self) -> None:
        self.engine.dispose()


def connect_warehouse(url: str) -> DuckDBWarehouse | PostgresWarehouse:
    if url.startswith("duckdb:///"):
        return DuckDBWarehouse(url.removeprefix("duckdb:///"))
    if url.startswith("postgresql"):
        return PostgresWarehouse(url)
    raise ValueError(f"Unsupported warehouse URL: {url.split(':', 1)[0]}")


def run_sql_file(wh: Warehouse, path: Path) -> None:
    """Execute a SQL script; a dialect-specific sibling file runs afterwards if present."""
    wh.execute(path.read_text())
    specific = path.with_suffix(f".{wh.dialect}.sql")
    if specific.is_file():
        wh.execute(specific.read_text())
