"""The ETL pipeline: ingest -> transform -> load, with batch tracking.

Each step is a plain function taking a ``Runtime`` and a ``BatchInfo``, so the
same code runs from the CLI, from tests and from Airflow tasks. Steps hand data
to each other only through storage (Bronze, Silver, reports), never in memory,
which is what makes a single step retryable on its own.
"""

from __future__ import annotations

import json
import os
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import Any, Protocol

import pandas as pd

from finflow.common.config import Settings
from finflow.common.errors import FinFlowError, QualityGateError, SimulatedFailure
from finflow.common.logging import get_logger, log_context
from finflow.common.storage import LakeStorage
from finflow.ingestion import bronze
from finflow.sources.files import FileSource
from finflow.sources.models import BatchInfo, RawExtract, list_landing_batches, load_landing_batch
from finflow.transformations.silver import EntityResult, TransformContext, transform_entity
from finflow.validation import quality
from finflow.validation.contracts import CONTRACTS, PROCESSING_ORDER
from finflow.warehouse.base import DuckDBWarehouse, PostgresWarehouse, connect_warehouse, run_sql_file

log = get_logger("pipeline")

ETL = "etl"
DIM_DATE_RANGE = (date(2024, 1, 1), date(2027, 12, 31))
LOAD_SCRIPTS = {
    "exchange_rates": "10_load_exchange_rates.sql",
    "merchants": "11_load_merchants.sql",
    "customers": "12_load_customers_scd2.sql",
    "accounts": "13_load_accounts.sql",
    "cards": "14_load_cards.sql",
    "loans": "15_load_loans.sql",
    "transactions": "20_load_fact_transactions.sql",
    "loan_payments": "21_load_fact_loan_payments.sql",
}


class ReconciliationError(FinFlowError):
    """Rows staged for loading did not all arrive in the target table."""


class Source(Protocol):
    def extract(self, entity: str, batch: BatchInfo, watermark: datetime | None) -> RawExtract | None: ...


def utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def new_run_id() -> str:
    """A new run id, unless an orchestrator supplies one (FINFLOW_RUN_ID).

    Airflow passes its own run_id, so every task of one DAG run shares an id:
    batch `attempts` count runs rather than task processes, and FinFlow logs
    can be joined with Airflow's.
    """
    return os.environ.get("FINFLOW_RUN_ID") or f"run-{utcnow():%Y%m%dT%H%M%S}-{uuid.uuid4().hex[:6]}"


def maybe_fail(step: str) -> None:
    """Failure injection for recovery drills: ``FINFLOW_FAIL_AT=load finflow etl ...``."""
    if os.environ.get("FINFLOW_FAIL_AT") == step:
        raise SimulatedFailure(f"Simulated failure at step '{step}' (FINFLOW_FAIL_AT)")


@dataclass
class Runtime:
    settings: Settings
    storage: LakeStorage
    warehouse: DuckDBWarehouse | PostgresWarehouse
    run_id: str = field(default_factory=new_run_id)


@contextmanager
def open_runtime(settings: Settings) -> Iterator[Runtime]:
    warehouse = connect_warehouse(settings.warehouse_url)
    try:
        runtime = Runtime(settings, LakeStorage.from_settings(settings), warehouse)
        init_warehouse(runtime)
        yield runtime
    finally:
        warehouse.close()


# --------------------------------------------------------------- warehouse setup
def init_warehouse(rt: Runtime) -> None:
    run_sql_file(rt.warehouse, rt.settings.sql_dir / "warehouse" / "01_schema.sql")
    run_sql_file(rt.warehouse, rt.settings.sql_dir / "staging" / "00_staging_schema.sql")
    if int(rt.warehouse.query("SELECT COUNT(*) AS n FROM dim_date")["n"].iloc[0]) == 0:
        days = pd.date_range(*DIM_DATE_RANGE, freq="D")
        frame = pd.DataFrame(
            {
                "date_key": days.strftime("%Y%m%d").astype(int),
                "full_date": days.date,
                "year": days.year,
                "quarter": days.quarter,
                "month": days.month,
                "month_name": days.month_name(),
                "day_of_month": days.day,
                "iso_day_of_week": days.day_of_week + 1,
                "is_weekend": days.day_of_week >= 5,
            }
        )
        with rt.warehouse.transaction():
            rt.warehouse.stage("stg_dim_date", frame)
            rt.warehouse.execute(
                "INSERT INTO dim_date SELECT date_key, CAST(full_date AS DATE), year, quarter, month, "
                "month_name, day_of_month, iso_day_of_week, is_weekend FROM stg_dim_date "
                "ON CONFLICT DO NOTHING"
            )


# ------------------------------------------------------------------- tracking
@dataclass
class StepMetrics:
    records_in: int | None = None
    records_out: int | None = None


@contextmanager
def track_step(rt: Runtime, pipeline: str, step: str, batch_id: str | None) -> Iterator[StepMetrics]:
    """Record every step attempt in ``fact_pipeline_execution``, including failures."""
    metrics = StepMetrics()
    started = utcnow()
    clock = time.perf_counter()
    status, error = "SUCCESS", None
    log.info("step started", extra={"pipeline": pipeline, "step": step})
    try:
        yield metrics
    except BaseException as exc:
        status, error = "FAILED", f"{type(exc).__name__}: {exc}"[:500]
        raise
    finally:
        duration_ms = int((time.perf_counter() - clock) * 1000)
        rt.warehouse.execute(
            "INSERT INTO fact_pipeline_execution (run_id, batch_id, pipeline, step, status, started_at, "
            "finished_at, duration_ms, records_in, records_out, error_message) VALUES (:run_id, :batch_id, "
            ":pipeline, :step, :status, :started_at, :finished_at, :duration_ms, :records_in, :records_out, "
            ":error_message)",
            {
                "run_id": rt.run_id,
                "batch_id": batch_id,
                "pipeline": pipeline,
                "step": step,
                "status": status,
                "started_at": started,
                "finished_at": utcnow(),
                "duration_ms": duration_ms,
                "records_in": metrics.records_in,
                "records_out": metrics.records_out,
                "error_message": error,
            },
        )
        log.info(
            "step finished",
            extra={
                "pipeline": pipeline,
                "step": step,
                "status": status,
                "duration_ms": duration_ms,
                "records_in": metrics.records_in,
                "records_out": metrics.records_out,
            },
        )


def set_batch_status(rt: Runtime, batch: BatchInfo, status: str) -> None:
    rt.warehouse.execute(
        "INSERT INTO etl_batch (batch_id, sequence, batch_type, business_date, status, attempts, "
        "last_run_id, updated_at) VALUES (:batch_id, :sequence, :batch_type, :business_date, :status, 1, "
        ":run_id, :now) ON CONFLICT (batch_id) DO UPDATE SET status = EXCLUDED.status, "
        "attempts = etl_batch.attempts + CASE WHEN etl_batch.last_run_id = EXCLUDED.last_run_id "
        "THEN 0 ELSE 1 END, last_run_id = EXCLUDED.last_run_id, updated_at = EXCLUDED.updated_at",
        {
            "batch_id": batch.batch_id,
            "sequence": batch.sequence,
            "batch_type": batch.batch_type,
            "business_date": batch.business_date,
            "status": status,
            "run_id": rt.run_id,
            "now": utcnow(),
        },
    )


def batch_statuses(rt: Runtime) -> dict[str, str]:
    frame = rt.warehouse.query("SELECT batch_id, status FROM etl_batch")
    return dict(zip(frame["batch_id"], frame["status"], strict=True))


def get_watermark(rt: Runtime, pipeline: str, entity: str) -> datetime | None:
    frame = rt.warehouse.query(
        "SELECT watermark_ts FROM etl_watermark WHERE pipeline = :pipeline AND entity = :entity",
        {"pipeline": pipeline, "entity": entity},
    )
    return None if frame.empty else pd.Timestamp(frame["watermark_ts"].iloc[0]).to_pydatetime()


# --------------------------------------------------------------------- ingest
def build_sources(settings: Settings) -> dict[str, Source]:
    """Which adapter extracts which entity, per execution mode."""
    files = _FileSourceAdapter(FileSource(settings.landing_dir))
    sources: dict[str, Source] = dict.fromkeys(CONTRACTS, files)
    if settings.mode == "data":
        from finflow.sources.api_client import ApiSource
        from finflow.sources.operational import OperationalSource

        assert settings.source_api_url and settings.ops_db_url
        api = ApiSource(settings.source_api_url)
        ops = OperationalSource(settings.ops_db_url)
        sources.update(dict.fromkeys(ApiSource.entities, api))
        sources.update(dict.fromkeys(OperationalSource.entities, ops))
    return sources


@dataclass
class _FileSourceAdapter:
    """Files are tracked per batch, so the watermark is not needed to read them."""

    source: FileSource

    def extract(self, entity: str, batch: BatchInfo, watermark: datetime | None) -> RawExtract | None:
        return self.source.extract(entity, batch)


def ingest(rt: Runtime, batch: BatchInfo, sources: dict[str, Source] | None = None) -> dict[str, Any]:
    """Land every source extract for the batch in Bronze. Idempotent."""
    existing = bronze.read_batch_marker(rt.storage, batch.batch_id)
    if existing is not None:
        log.info("batch already in Bronze; replaying from Bronze")
        return existing
    sources = sources or build_sources(rt.settings)
    written: list[bronze.BronzeEntity] = []
    for entity in PROCESSING_ORDER:
        if entity not in batch.entities:
            continue
        watermark = get_watermark(rt, ETL, entity)
        extract = sources[entity].extract(entity, batch, watermark)
        if extract is not None:
            written.append(bronze.write_entity(rt.storage, batch, extract, watermark))
    maybe_fail("ingest")
    bronze.write_batch_marker(rt.storage, batch, written)
    marker = bronze.read_batch_marker(rt.storage, batch.batch_id)
    assert marker is not None
    return marker


# ------------------------------------------------------------------ transform
def silver_prefix(entity: str) -> str:
    return f"silver/{entity}/"


def _silver_files(
    rt: Runtime, entity: str, *, only: str | None = None, exclude: str | None = None
) -> list[str]:
    files = rt.storage.list_files(silver_prefix(entity))
    if only is not None:
        files = [f for f in files if f"batch_id={only}" in f]
    if exclude is not None:
        files = [f for f in files if f"batch_id={exclude}" not in f]
    return files


def _reference_context(rt: Runtime, batch: BatchInfo, window_ctx: TransformContext) -> None:
    """Load keys accepted by earlier batches, so referential checks see the whole lake."""
    for entity in ("customers", "accounts", "merchants", "cards", "loans"):
        key = CONTRACTS[entity].natural_key
        frame = rt.storage.read_parquet(_silver_files(rt, entity, exclude=batch.batch_id), columns=[key])
        window_ctx.known_keys[entity] = set(frame[key].dropna()) if len(frame) else set()
    owners = rt.storage.read_parquet(
        _silver_files(rt, "accounts", exclude=batch.batch_id), columns=["account_id", "customer_id"]
    )
    window_ctx.account_owner = dict(zip(owners["account_id"], owners["customer_id"], strict=True))
    window_ctx.rates = rt.storage.read_parquet(
        _silver_files(rt, "exchange_rates", exclude=batch.batch_id),
        columns=["currency_code", "rate_date", "rate_to_mxn_micros"],
    )


def validate(rt: Runtime, batch: BatchInfo) -> dict[str, Any]:
    """Run every validation rule and the quality gate without writing to Silver.

    Lets an orchestrator fail fast on a bad batch before any derived data exists.
    """
    return transform(rt, batch, write_silver=False)


def transform(rt: Runtime, batch: BatchInfo, *, write_silver: bool = True) -> dict[str, Any]:
    """Bronze -> Silver for one batch. Writes nothing to Silver if the quality gate fails."""
    marker = bronze.read_batch_marker(rt.storage, batch.batch_id)
    if marker is None:
        raise FinFlowError(f"Batch {batch.batch_id} is not in Bronze yet; run ingest first.")
    objects = {obj["entity"]: obj for obj in marker["objects"]}
    ctx = TransformContext(
        batch_id=batch.batch_id,
        source_system="",
        ingested_at=datetime.fromisoformat(marker["completed_at"]),
        window_start=batch.window_start,
        window_end=batch.window_end,
        risk=rt.settings.risk,
    )
    _reference_context(rt, batch, ctx)

    results: list[EntityResult] = []
    for entity in PROCESSING_ORDER:
        if entity not in objects:
            continue
        ctx.source_system = objects[entity]["source_system"]
        records = bronze.read_entity_records(rt.storage, objects[entity])
        result = transform_entity(CONTRACTS[entity], records, ctx)
        results.append(result)
        # Make this batch's accepted keys visible to the entities that follow.
        key = CONTRACTS[entity].natural_key
        ctx.known_keys.setdefault(entity, set()).update(result.accepted[key].dropna())
        if entity == "accounts":
            ctx.account_owner.update(
                zip(result.accepted["account_id"], result.accepted["customer_id"], strict=True)
            )
        if entity == "exchange_rates":
            ctx.rates = pd.concat([ctx.rates, result.accepted[ctx.rates.columns]], ignore_index=True)

    rows, critical, report = quality.evaluate(
        results, rt.settings.quality, batch.batch_id, rt.run_id, utcnow()
    )
    _write_quality_report(rt, batch, report, rows)
    for result in results:  # quarantine is written even when the gate fails: it explains why
        _write_quarantine(rt, batch, result)
    if critical:
        raise QualityGateError("; ".join(critical))
    if write_silver:
        for result in results:
            _write_silver(rt, batch, result)
    return report


def _write_quality_report(rt: Runtime, batch: BatchInfo, report: dict[str, Any], rows: pd.DataFrame) -> None:
    base = f"reports/quality/{batch.batch_id}"
    rt.storage.write_bytes(f"{base}/report.json", json.dumps(report, indent=2, default=str).encode())
    rt.storage.write_parquet(rows, f"{base}/rules.parquet")


def _write_quarantine(rt: Runtime, batch: BatchInfo, result: EntityResult) -> None:
    path = f"rejected/{result.entity}/batch_id={batch.batch_id}.parquet"
    if len(result.quarantine):
        rt.storage.write_parquet(result.quarantine, path)


def _write_silver(rt: Runtime, batch: BatchInfo, result: EntityResult) -> None:
    # Silver is derived data: reprocessing replaces this batch's files exactly.
    for stale in _silver_files(rt, result.entity, only=batch.batch_id):
        rt.storage.delete_file(stale)
    if result.accepted.empty:
        return
    if result.entity == "transactions":
        # The partition key lives only in the path (Hive convention). Storing it in
        # the file as well makes partition-aware readers see two conflicting columns.
        for day, part in result.accepted.groupby(result.accepted["txn_date"].dt.date):
            rt.storage.write_parquet(
                part.drop(columns=["txn_date"]),
                f"silver/transactions/txn_date={day}/batch_id={batch.batch_id}.parquet",
            )
    else:
        rt.storage.write_parquet(result.accepted, f"silver/{result.entity}/batch_id={batch.batch_id}.parquet")


# ----------------------------------------------------------------------- load
def _staging_frame(entity: str, df: pd.DataFrame, loaded_at: datetime) -> pd.DataFrame:
    """Add the warehouse-only columns (date keys, effective timestamps) to a Silver frame."""
    out = df.copy()
    out["loaded_at"] = pd.Timestamp(loaded_at).as_unit("us")
    if entity == "transactions":
        out["date_key"] = out["event_ts"].dt.strftime("%Y%m%d").astype("int64")
    if entity == "loan_payments":
        out["due_date_key"] = out["due_date"].dt.strftime("%Y%m%d").astype("int64")
        out["paid_date_key"] = pd.to_numeric(out["paid_at"].dt.strftime("%Y%m%d"), errors="coerce").astype(
            "Int64"
        )
        late = (out["paid_at"].dt.normalize() - out["due_date"]).dt.days
        out["days_late"] = late.clip(lower=0).astype("Int64")
        out["effective_ts"] = out["paid_at"].fillna(out["due_date"])
    return out


def load(rt: Runtime, batch: BatchInfo) -> dict[str, int]:
    """Silver -> warehouse in one transaction. Watermarks move only if it commits."""
    sql_dir = rt.settings.sql_dir / "warehouse"
    loaded_at = utcnow()
    frames = {
        entity: rt.storage.read_parquet(_silver_files(rt, entity, only=batch.batch_id))
        for entity in PROCESSING_ORDER
    }
    marker = bronze.read_batch_marker(rt.storage, batch.batch_id)
    assert marker is not None
    quality_rows = rt.storage.read_parquet([f"reports/quality/{batch.batch_id}/rules.parquet"])
    counts: dict[str, int] = {}

    with rt.warehouse.transaction():
        for entity in PROCESSING_ORDER:
            frame = frames[entity]
            if frame.empty:
                continue
            rt.warehouse.stage(f"stg_{entity}", _staging_frame(entity, frame, loaded_at))
            run_sql_file(rt.warehouse, sql_dir / LOAD_SCRIPTS[entity])
            counts[entity] = len(frame)
        _reconcile_facts(rt, frames)
        if not quality_rows.empty:
            rt.warehouse.stage("stg_data_quality", quality_rows)
            run_sql_file(rt.warehouse, sql_dir / "30_load_data_quality.sql")
        # The watermark is the end of the extraction window: everything up to it is
        # now committed. It is written inside the same transaction as the data.
        for obj in marker["objects"]:
            rt.warehouse.execute(
                "INSERT INTO etl_watermark (pipeline, entity, watermark_ts, batch_id, updated_at) "
                "VALUES (:pipeline, :entity, :ts, :batch_id, :now) ON CONFLICT (pipeline, entity) DO UPDATE "
                "SET watermark_ts = EXCLUDED.watermark_ts, batch_id = EXCLUDED.batch_id, "
                "updated_at = EXCLUDED.updated_at WHERE EXCLUDED.watermark_ts > etl_watermark.watermark_ts",
                {
                    "pipeline": ETL,
                    "entity": obj["entity"],
                    "ts": batch.window_end,
                    "batch_id": batch.batch_id,
                    "now": loaded_at,
                },
            )
        maybe_fail("load")  # inside the transaction: a failure here rolls everything back
    return counts


def _reconcile_facts(rt: Runtime, frames: dict[str, pd.DataFrame]) -> None:
    """Every staged fact row must be in the target with the same amount (no silent join loss)."""
    checks = (
        ("transactions", "fact_transactions", "transaction_id", "amount_minor", "amount_minor"),
        ("loan_payments", "fact_loan_payments", "payment_id", "amount_paid_minor", "amount_minor"),
    )
    for entity, table, key, target_amount, staged_amount in checks:
        if frames[entity].empty:
            continue
        result = rt.warehouse.query(
            f"SELECT COUNT(*) AS n, COALESCE(SUM(f.{target_amount}), 0) AS amount "
            f"FROM {table} f JOIN stg_{entity} s ON s.{key} = f.{key}"
        )
        expected_n = len(frames[entity])
        expected_amount = int(frames[entity][staged_amount].sum())
        got_n, got_amount = int(result["n"].iloc[0]), int(result["amount"].iloc[0])
        if (got_n, got_amount) != (expected_n, expected_amount):
            raise ReconciliationError(
                f"{table}: staged {expected_n} rows / {expected_amount} minor units, "
                f"found {got_n} rows / {got_amount}"
            )
    # Counts and sums cannot see a fact attached to the wrong SCD2 version (e.g. a
    # join that lost its validity condition), so check point-in-time correctness too.
    if not frames["transactions"].empty:
        wrong_version = rt.warehouse.query(
            "SELECT COUNT(*) AS n FROM fact_transactions f "
            "JOIN stg_transactions s ON s.transaction_id = f.transaction_id "
            "JOIN dim_customer c ON c.customer_key = f.customer_key "
            "WHERE NOT (f.event_ts >= c.valid_from AND (c.valid_to IS NULL OR f.event_ts < c.valid_to))"
        )
        bad = int(wrong_version["n"].iloc[0])
        if bad:
            raise ReconciliationError(
                f"fact_transactions: {bad} rows point at a customer version not valid at event time"
            )


# ------------------------------------------------------------------- pipeline
def resolve_batches(settings: Settings, batch_id: str | None) -> list[BatchInfo]:
    if batch_id:
        return [load_landing_batch(settings.landing_dir, batch_id)]
    return list_landing_batches(settings.landing_dir)


def run_etl(rt: Runtime, batch: BatchInfo, *, force: bool = False) -> dict[str, Any]:
    """Run ingest, transform and load for one batch, recording status and metrics."""
    with log_context(run_id=rt.run_id, batch_id=batch.batch_id):
        if not force and batch_statuses(rt).get(batch.batch_id) == "LOADED":
            log.info("batch already loaded; skipping (use --force to reprocess)")
            return {"batch_id": batch.batch_id, "status": "SKIPPED"}
        try:
            with track_step(rt, ETL, "ingest", batch.batch_id) as m:
                marker = ingest(rt, batch)
                m.records_out = sum(o["record_count"] for o in marker["objects"])
            set_batch_status(rt, batch, "INGESTED")
            with track_step(rt, ETL, "transform", batch.batch_id) as m:
                m.records_in = sum(o["record_count"] for o in marker["objects"])
                report = transform(rt, batch)
                m.records_out = sum(e["accepted"] for e in report["entities"].values())
            set_batch_status(rt, batch, "TRANSFORMED")
            with track_step(rt, ETL, "load", batch.batch_id) as m:
                counts = load(rt, batch)
                m.records_in = m.records_out = sum(counts.values())
            set_batch_status(rt, batch, "LOADED")
        except QualityGateError:
            _record_failed_quality(rt, batch)
            set_batch_status(rt, batch, "QUALITY_FAILED")
            raise
        except BaseException:
            set_batch_status(rt, batch, "FAILED")
            raise
        return {"batch_id": batch.batch_id, "status": "LOADED", "loaded": counts, "quality": report}


def _record_failed_quality(rt: Runtime, batch: BatchInfo) -> None:
    """A gated batch loads nothing, but its quality measurements are still recorded."""
    rows = rt.storage.read_parquet([f"reports/quality/{batch.batch_id}/rules.parquet"])
    with rt.warehouse.transaction():
        rt.warehouse.stage("stg_data_quality", rows)
        run_sql_file(rt.warehouse, rt.settings.sql_dir / "warehouse" / "30_load_data_quality.sql")


def run_pending(rt: Runtime, *, force: bool = False, until: date | None = None) -> list[dict[str, Any]]:
    """Process landing batches in sequence order; stop at the first failure."""
    statuses = batch_statuses(rt)
    results = []
    for batch in list_landing_batches(rt.settings.landing_dir):
        if until is not None and batch.business_date > until:
            break
        if statuses.get(batch.batch_id) == "LOADED" and not force:
            continue
        results.append(run_etl(rt, batch, force=force))
    return results


def backfill(rt: Runtime, start: date, end: date) -> list[dict[str, Any]]:
    """Reprocess every batch whose business date is in [start, end], from Bronze."""
    batches = [b for b in list_landing_batches(rt.settings.landing_dir) if start <= b.business_date <= end]
    return [run_etl(rt, b, force=True) for b in batches]
