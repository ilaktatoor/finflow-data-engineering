"""Small, reproducible performance comparisons on the project's own data.

These numbers are educational. At a few thousand rows, fixed overheads
dominate, so they say nothing about behaviour at enterprise scale. Each
measurement is the median of several runs on the current machine; nothing here
is hard-coded or extrapolated.
"""

from __future__ import annotations

import json
import platform
import statistics
import tempfile
import time
import tracemalloc
from collections.abc import Callable
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd

from finflow.common.config import Settings
from finflow.common.errors import FinFlowError
from finflow.common.money import convert_minor
from finflow.common.storage import LakeStorage

REPEATS = 5


def median_ms(fn: Callable[[], object], repeats: int = REPEATS) -> float:
    timings = []
    for _ in range(repeats):
        start = time.perf_counter()
        fn()
        timings.append((time.perf_counter() - start) * 1000)
    return round(statistics.median(timings), 3)


def load_silver_transactions(settings: Settings) -> pd.DataFrame:
    storage = LakeStorage.from_settings(settings)
    files = storage.list_files("silver/transactions/")
    if not files:
        raise FinFlowError("No Silver transactions yet: run `finflow etl` (or `make demo`) first.")
    df = storage.read_parquet(files)
    df["txn_date"] = df["event_ts"].dt.normalize()  # partition key, not stored in the files
    return df


def bench_csv_vs_parquet(df: pd.DataFrame, workdir: Path) -> dict[str, Any]:
    csv_path, parquet_path = workdir / "t.csv", workdir / "t.parquet"
    df.to_csv(csv_path, index=False)
    df.to_parquet(parquet_path, index=False, compression="zstd")
    columns = ["currency_code", "amount_mxn_minor"]
    return {
        "rows": len(df),
        "csv_bytes": csv_path.stat().st_size,
        "parquet_bytes": parquet_path.stat().st_size,
        "read_all_columns_ms": {
            "csv": median_ms(lambda: pd.read_csv(csv_path)),
            "parquet": median_ms(lambda: pd.read_parquet(parquet_path)),
        },
        "read_two_columns_ms": {
            "csv": median_ms(lambda: pd.read_csv(csv_path, usecols=columns)),
            "parquet": median_ms(lambda: pd.read_parquet(parquet_path, columns=columns)),
        },
        "note": "CSV also loses types: amounts come back as int64/float, timestamps as text.",
    }


def bench_vectorized_vs_loop(df: pd.DataFrame) -> dict[str, Any]:
    amounts, rates = df["amount_minor"], df["rate_micros"]

    def row_by_row() -> list[int]:
        out = []
        for _, row in df[["amount_minor", "rate_micros"]].iterrows():
            value = Decimal(int(row["amount_minor"])) * Decimal(int(row["rate_micros"])) / Decimal(1_000_000)
            out.append(int(value.quantize(Decimal("1"), rounding=ROUND_HALF_UP)))
        return out

    vectorized = convert_minor(amounts, rates)
    assert vectorized.tolist() == row_by_row(), "both implementations must agree before timing them"
    loop_ms = median_ms(row_by_row, repeats=3)
    vector_ms = median_ms(lambda: convert_minor(amounts, rates))
    return {
        "rows": len(df),
        "iterrows_decimal_ms": loop_ms,
        "vectorized_int64_ms": vector_ms,
        "speedup": round(loop_ms / vector_ms, 1) if vector_ms else None,
    }


def bench_chunked(df: pd.DataFrame, workdir: Path) -> dict[str, Any]:
    csv_path = workdir / "chunks.csv"
    df[["currency_code", "amount_mxn_minor"]].to_csv(csv_path, index=False)

    def full() -> pd.Series:
        return pd.read_csv(csv_path).groupby("currency_code")["amount_mxn_minor"].sum()

    def chunked(size: int = 250) -> pd.Series:
        partials = [
            chunk.groupby("currency_code")["amount_mxn_minor"].sum()
            for chunk in pd.read_csv(csv_path, chunksize=size)
        ]
        return pd.concat(partials).groupby(level=0).sum()

    assert full().equals(chunked()), "chunked aggregation must match the full aggregation"

    def peak_kib(fn: Callable[[], object]) -> int:
        tracemalloc.start()
        fn()
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        return peak // 1024

    return {
        "rows": len(df),
        "chunk_size": 250,
        "full_ms": median_ms(full),
        "chunked_ms": median_ms(chunked),
        "full_peak_kib": peak_kib(full),
        "chunked_peak_kib": peak_kib(chunked),
    }


def bench_memory_dtypes(df: pd.DataFrame) -> dict[str, Any]:
    low_cardinality = ["currency_code", "status", "channel", "transaction_type"]
    as_object = df[low_cardinality].astype(object)
    as_category = df[low_cardinality].astype("category")
    return {
        "columns": low_cardinality,
        "object_bytes": int(as_object.memory_usage(deep=True).sum()),
        "category_bytes": int(as_category.memory_usage(deep=True).sum()),
    }


def bench_index(df: pd.DataFrame) -> dict[str, Any]:
    """Point lookups by transaction_id with and without an ART index (DuckDB)."""
    # Silver keeps one row per batch, so corrected transactions appear twice;
    # the warehouse keeps the latest version, and so does this benchmark.
    df = df.sort_values("batch_id").drop_duplicates("transaction_id", keep="last")
    ids = df["transaction_id"].sample(n=min(200, len(df)), random_state=1).tolist()
    results = {}
    for label in ("no_index", "art_index"):
        con = duckdb.connect()
        con.register("src", df[["transaction_id", "amount_minor"]])
        con.execute("CREATE TABLE t AS SELECT * FROM src")
        if label == "art_index":
            con.execute("CREATE UNIQUE INDEX ux_t ON t (transaction_id)")

        def lookups(c: duckdb.DuckDBPyConnection = con) -> None:
            for i in ids:
                c.execute("SELECT amount_minor FROM t WHERE transaction_id = ?", [i]).fetchone()

        results[f"{label}_ms_for_{len(ids)}_lookups"] = median_ms(lookups, repeats=3)
        con.close()
    return results


def bench_incremental_vs_full(df: pd.DataFrame) -> dict[str, Any]:
    """Rebuild a daily aggregate from scratch vs. upsert only the newest day."""
    con = duckdb.connect()
    con.register("silver", df[["txn_date", "amount_mxn_minor"]])
    con.execute("CREATE TABLE facts AS SELECT * FROM silver")
    con.execute("CREATE TABLE daily (txn_date TIMESTAMP PRIMARY KEY, total BIGINT, n BIGINT)")
    newest = df["txn_date"].max()

    def full() -> None:
        con.execute("DELETE FROM daily")
        con.execute(
            "INSERT INTO daily SELECT txn_date, SUM(amount_mxn_minor), COUNT(*) FROM facts GROUP BY 1"
        )

    def incremental() -> None:
        con.execute(
            "INSERT INTO daily SELECT txn_date, SUM(amount_mxn_minor), COUNT(*) FROM facts "
            "WHERE txn_date >= ? GROUP BY 1 ON CONFLICT (txn_date) DO UPDATE SET total = EXCLUDED.total, "
            "n = EXCLUDED.n",
            [newest],
        )

    full()
    result = {
        "days": int(df["txn_date"].nunique()),
        "full_rebuild_ms": median_ms(full),
        "incremental_one_day_ms": median_ms(incremental),
    }
    con.close()
    return result


def run_all(settings: Settings) -> dict[str, Any]:
    df = load_silver_transactions(settings)
    with tempfile.TemporaryDirectory() as tmp:
        workdir = Path(tmp)
        results: dict[str, Any] = {
            "environment": {
                "python": platform.python_version(),
                "pandas": pd.__version__,
                "duckdb": duckdb.__version__,
                "machine": platform.machine(),
                "repeats": REPEATS,
                "statistic": "median",
            },
            "csv_vs_parquet": bench_csv_vs_parquet(df, workdir),
            "vectorized_vs_row_by_row": bench_vectorized_vs_loop(df),
            "chunked_processing": bench_chunked(df, workdir),
            "memory_object_vs_category": bench_memory_dtypes(df),
            "indexed_vs_non_indexed_lookups": bench_index(df),
            "incremental_vs_full_refresh": bench_incremental_vs_full(df),
        }
    out = settings.reports_dir / "benchmarks.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(results, indent=2))
    results["written_to"] = str(out)
    return results
