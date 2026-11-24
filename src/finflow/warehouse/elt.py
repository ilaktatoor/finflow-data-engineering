"""ELT path: load raw transactions untyped, transform them with SQL in the warehouse.

Compare with the ETL path (``finflow.orchestration.pipeline``), where Pandas
types and validates the data *before* it reaches the warehouse.
"""

from __future__ import annotations

import json
from typing import Any

import pandas as pd

from finflow.common.errors import FinFlowError
from finflow.common.logging import log_context
from finflow.ingestion import bronze
from finflow.orchestration.pipeline import Runtime, track_step, utcnow
from finflow.sources.models import BatchInfo
from finflow.validation.contracts import CONTRACTS
from finflow.warehouse.base import run_sql_file

ELT = "elt"
RAW_COLUMNS = list(CONTRACTS["transactions"].columns)


def load_raw(rt: Runtime, batch: BatchInfo) -> int:
    """Copy this batch's raw transactions from Bronze into ``stg_raw_transactions``. Idempotent."""
    marker = bronze.read_batch_marker(rt.storage, batch.batch_id)
    if marker is None:
        raise FinFlowError(f"Batch {batch.batch_id} is not in Bronze; run the ETL ingest step first.")
    objects = [o for o in marker["objects"] if o["entity"] == "transactions"]
    if not objects:
        return 0
    records = bronze.read_entity_records(rt.storage, objects[0])
    frame = pd.DataFrame(
        [{c: None if r.get(c) is None else str(r[c]) for c in RAW_COLUMNS} for r in records],
        columns=RAW_COLUMNS,
    ).astype("string")
    frame.insert(0, "record_position", range(len(frame)))
    frame.insert(0, "batch_id", batch.batch_id)
    frame["raw_record"] = [json.dumps(r, sort_keys=True, ensure_ascii=False) for r in records]
    frame["loaded_at"] = pd.Timestamp(utcnow()).as_unit("us")
    columns = ", ".join(frame.columns)
    with rt.warehouse.transaction():
        rt.warehouse.stage("stg_raw_batch", frame)
        # (batch_id, record_position) is unique: reloading a batch inserts nothing.
        rt.warehouse.execute(
            f"INSERT INTO stg_raw_transactions ({columns}) SELECT {columns} FROM stg_raw_batch "
            "ON CONFLICT (batch_id, record_position) DO NOTHING"
        )
    return len(frame)


def transform_sql(rt: Runtime) -> dict[str, int]:
    """Run the incremental SQL transformation in one transaction."""
    staging = rt.settings.sql_dir / "staging"
    with rt.warehouse.transaction():
        run_sql_file(rt.warehouse, staging / "10_elt_check_new_transactions.sql")
        counts = rt.warehouse.query(
            "SELECT COUNT(*) AS processed, "
            "SUM(CASE WHEN rejection_reason IS NULL AND occurrence = 1 THEN 1 ELSE 0 END) AS accepted "
            "FROM elt_work_checked"
        )
        run_sql_file(rt.warehouse, staging / "20_elt_merge_transactions.sql")
    return {
        "processed": int(counts["processed"].iloc[0]),
        "accepted": int(counts["accepted"].fillna(0).iloc[0]),
    }


def refresh_marts(rt: Runtime) -> list[str]:
    """Rebuild every data mart (they are small, so a full rebuild is the simple choice)."""
    built = []
    with rt.warehouse.transaction():
        for path in sorted((rt.settings.sql_dir / "marts").glob("[0-9]*.sql")):
            if path.name.count(".") > 1:  # engine-specific siblings run via run_sql_file
                continue
            run_sql_file(rt.warehouse, path)
            built.append(path.stem)
    return built


def reconcile(rt: Runtime) -> pd.DataFrame:
    """Days where the ETL star schema and the ELT tables disagree (empty = consistent)."""
    sql = (rt.settings.sql_dir / "quality" / "etl_elt_reconciliation.sql").read_text()
    return rt.warehouse.query(sql)


def run_elt(rt: Runtime, batch: BatchInfo) -> dict[str, Any]:
    with log_context(run_id=rt.run_id, batch_id=batch.batch_id):
        with track_step(rt, ELT, "load_raw", batch.batch_id) as m:
            m.records_out = load_raw(rt, batch)
        with track_step(rt, ELT, "transform_sql", batch.batch_id) as m:
            counts = transform_sql(rt)
            m.records_in, m.records_out = counts["processed"], counts["accepted"]
        return {"batch_id": batch.batch_id, "raw_rows": m.records_in, **counts}
