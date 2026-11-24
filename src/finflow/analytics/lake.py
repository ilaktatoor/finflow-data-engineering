"""DuckDB as an analytical engine directly on the Parquet lake.

No load step and no warehouse: DuckDB reads the Silver/rejected Parquet files
where they are. In lightweight mode it scans the files itself (hive partitions
become columns and are pruned by the WHERE clause); in data mode the files
live in MinIO and are handed over through PyArrow's S3 filesystem.
"""

from __future__ import annotations

import duckdb
import pandas as pd
import pyarrow as pa
import pyarrow.dataset as ds

from finflow.common.config import Settings
from finflow.common.storage import LakeStorage

LAKE_QUERIES = {
    "Daily volume for the first week of January (partition pruning on txn_date)": """
        SELECT txn_date, COUNT(*) AS transactions, SUM(amount_mxn_minor) AS gross_mxn_minor
        FROM silver_transactions
        WHERE txn_date BETWEEN DATE '2026-01-01' AND DATE '2026-01-07'
        GROUP BY txn_date ORDER BY txn_date""",
    "Transaction volume by currency": """
        SELECT currency_code, COUNT(*) AS transactions, SUM(amount_minor) AS original_minor,
               SUM(amount_mxn_minor) AS amount_mxn_minor
        FROM silver_transactions GROUP BY currency_code ORDER BY transactions DESC""",
    "Why records were rejected (one reason per row)": """
        SELECT entity, reason, COUNT(*) AS records
        FROM (SELECT entity, UNNEST(string_split(reasons, '|')) AS reason FROM rejected)
        GROUP BY entity, reason ORDER BY records DESC, reason""",
    "Simulated risk flags by rule": """
        SELECT reason, COUNT(*) AS flagged
        FROM (SELECT UNNEST(string_split(risk_reasons, '|')) AS reason
              FROM silver_transactions WHERE is_risk_flagged)
        GROUP BY reason ORDER BY flagged DESC""",
    "Rows per batch in Silver (lineage columns)": """
        SELECT batch_id, source_system, COUNT(*) AS rows, MIN(ingested_at) AS ingested_at
        FROM silver_transactions GROUP BY batch_id, source_system ORDER BY batch_id""",
}


def lake_connection(settings: Settings) -> duckdb.DuckDBPyConnection:
    con = duckdb.connect()
    con.execute("SET integer_division = true")
    storage = LakeStorage.from_settings(settings)
    if storage.is_local:
        # CREATE VIEW cannot take bound parameters; the path comes from our own
        # settings, and quotes are escaped anyway.
        root = str(settings.lake_dir).replace("'", "''")
        con.execute(
            "CREATE VIEW silver_transactions AS SELECT * FROM read_parquet("
            f"'{root}/silver/transactions/*/*.parquet', hive_partitioning = true, union_by_name = true)"
        )
        con.execute(
            f"CREATE VIEW rejected AS SELECT * FROM read_parquet('{root}/rejected/*/*.parquet', "
            "union_by_name = true)"
        )
    else:
        transactions = ds.dataset(
            f"{storage.root}/silver/transactions",
            filesystem=storage.fs,
            format="parquet",
            partitioning=ds.partitioning(pa.schema([("txn_date", pa.date32())]), flavor="hive"),
        )
        rejected = ds.dataset(f"{storage.root}/rejected", filesystem=storage.fs, format="parquet")
        con.register("silver_transactions", transactions)
        con.register("rejected", rejected)
    return con


def run_lake_queries(settings: Settings) -> dict[str, pd.DataFrame]:
    con = lake_connection(settings)
    try:
        return {title: con.execute(sql).df() for title, sql in LAKE_QUERIES.items()}
    finally:
        con.close()
