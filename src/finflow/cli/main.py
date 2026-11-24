"""``finflow`` command line. Every pipeline capability is reachable from here.

Run ``finflow --help`` or ``finflow <command> --help``. The Makefile and the
Airflow DAGs call these same commands.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd

from finflow.common.config import Settings, load_settings
from finflow.common.errors import FinFlowError, QualityGateError
from finflow.common.logging import configure_logging
from finflow.common.money import format_minor
from finflow.generators.synthetic import (
    HISTORICAL_BATCH_ID,
    SyntheticGenerator,
    next_incremental_sequence,
    write_batch,
)
from finflow.orchestration import pipeline
from finflow.sources.models import list_landing_batches, load_landing_batch


def _print(data: Any) -> None:
    print(json.dumps(data, indent=2, default=str))


def _frame(df: pd.DataFrame) -> None:
    print(df.to_string(index=False) if len(df) else "(no rows)")


# ------------------------------------------------------------------ commands
def cmd_generate(settings: Settings, args: argparse.Namespace) -> None:
    if (settings.landing_dir / HISTORICAL_BATCH_ID).exists() and not args.force:
        raise FinFlowError("Landing data already exists. Use --force or `finflow clean-generated`.")
    if args.force and settings.landing_dir.exists():
        shutil.rmtree(settings.landing_dir)
    config = settings.generation
    if args.error_rate is not None:
        from dataclasses import replace

        config = replace(config, error_rate=args.error_rate)
    generator = SyntheticGenerator(config, args.profile)
    batch = generator.historical_batch()
    path = write_batch(batch, settings.landing_dir, args.profile, config.seed)
    _print({"written": str(path), **batch.report})


def _profile_of_landing(settings: Settings) -> str:
    manifest = json.loads((settings.landing_dir / HISTORICAL_BATCH_ID / "_batch.json").read_text())
    return str(manifest["profile"])


def cmd_generate_incremental(settings: Settings, args: argparse.Namespace) -> None:
    generator = SyntheticGenerator(settings.generation, _profile_of_landing(settings))
    for _ in range(args.count):
        sequence = next_incremental_sequence(settings.landing_dir)
        batch = generator.incremental_batch(sequence)
        write_batch(batch, settings.landing_dir, generator.profile, settings.generation.seed)
        # --quiet prints only the batch id: Airflow passes it on through XCom.
        if args.quiet:
            print(batch.batch_id)
        else:
            _print(batch.report)


def cmd_seed(settings: Settings, args: argparse.Namespace) -> None:
    from finflow.sources.operational import seed_batch

    if settings.ops_db_url is None:
        raise FinFlowError("`seed` writes the operational PostgreSQL database: run it with --mode data.")
    batches = pipeline.resolve_batches(settings, args.batch)
    schema = settings.sql_dir / "operational" / "schema.sql"
    for batch in batches:
        _print(
            {
                "batch_id": batch.batch_id,
                "seeded": seed_batch(settings.ops_db_url, settings.landing_dir, batch, schema),
            }
        )


def cmd_etl(settings: Settings, args: argparse.Namespace) -> None:
    with pipeline.open_runtime(settings) as rt:
        if args.batch:
            results = [
                pipeline.run_etl(rt, load_landing_batch(settings.landing_dir, args.batch), force=args.force)
            ]
        else:
            results = pipeline.run_pending(rt, force=args.force, until=args.until)
        _print([_summary(r) for r in results] or "nothing to process")


def _summary(result: dict[str, Any]) -> dict[str, Any]:
    quality = result.get("quality", {})
    return {
        "batch_id": result["batch_id"],
        "status": result["status"],
        "loaded": result.get("loaded"),
        "quality": {
            k: {m: v[m] for m in ("input", "accepted", "rejected", "duplicates")}
            for k, v in quality.get("entities", {}).items()
        },
    }


def cmd_step(settings: Settings, args: argparse.Namespace) -> None:
    """Run one ETL step for one batch (used by Airflow so each step retries independently)."""
    batch = load_landing_batch(settings.landing_dir, args.batch)
    with pipeline.open_runtime(settings) as rt:
        step = {
            "ingest": pipeline.ingest,
            "validate": pipeline.validate,
            "transform": pipeline.transform,
            "load": pipeline.load,
        }[args.step]
        status = {
            "ingest": "INGESTED",
            "validate": "VALIDATED",
            "transform": "TRANSFORMED",
            "load": "LOADED",
        }[args.step]
        try:
            with pipeline.track_step(rt, pipeline.ETL, args.step, batch.batch_id):
                result = step(rt, batch)
        except QualityGateError:
            pipeline._record_failed_quality(rt, batch)
            pipeline.set_batch_status(rt, batch, "QUALITY_FAILED")
            raise
        except BaseException:
            pipeline.set_batch_status(rt, batch, "FAILED")
            raise
        pipeline.set_batch_status(rt, batch, status)
        _print(
            {
                "batch_id": batch.batch_id,
                "step": args.step,
                "status": status,
                "result": result if args.step == "load" else None,
            }
        )


def cmd_elt(settings: Settings, args: argparse.Namespace) -> None:
    from finflow.ingestion.bronze import read_batch_marker
    from finflow.warehouse import elt

    with pipeline.open_runtime(settings) as rt:
        batches = pipeline.resolve_batches(settings, args.batch)
        results = [
            elt.run_elt(rt, b) for b in batches if read_batch_marker(rt.storage, b.batch_id) is not None
        ]
        built = elt.refresh_marts(rt)
        mismatches = elt.reconcile(rt)
        _print({"batches": results, "marts": built, "reconciliation_mismatched_days": len(mismatches)})
        if len(mismatches):
            _frame(mismatches)


def cmd_marts(settings: Settings, args: argparse.Namespace) -> None:
    from finflow.warehouse import elt

    with pipeline.open_runtime(settings) as rt:
        _print({"marts": elt.refresh_marts(rt)})


def cmd_status(settings: Settings, args: argparse.Namespace) -> None:
    with pipeline.open_runtime(settings) as rt:
        print("Landing batches:", [b.batch_id for b in list_landing_batches(settings.landing_dir)])
        print("\nBatch status:")
        _frame(
            rt.warehouse.query(
                "SELECT batch_id, status, attempts, last_run_id FROM etl_batch ORDER BY sequence"
            )
        )
        print("\nWatermarks:")
        _frame(
            rt.warehouse.query(
                "SELECT pipeline, entity, watermark_ts, batch_id FROM etl_watermark ORDER BY 1, 2"
            )
        )
        print("\nWarehouse row counts:")
        tables = [
            "dim_customer",
            "dim_account",
            "dim_merchant",
            "dim_card",
            "dim_loan",
            "ref_exchange_rate",
            "fact_transactions",
            "fact_loan_payments",
            "fact_data_quality",
            "fact_pipeline_execution",
        ]
        union = " UNION ALL ".join(
            f"SELECT '{t}' AS table_name, COUNT(*) AS row_count FROM {t}" for t in tables
        )
        _frame(rt.warehouse.query(union))


def cmd_quality_report(settings: Settings, args: argparse.Namespace) -> None:
    with pipeline.open_runtime(settings) as rt:
        # `:batch` is NULL when no batch is given, which disables the filter.
        params = {"batch": args.batch}
        batch_filter = "(CAST(:batch AS VARCHAR) IS NULL OR q.batch_id = :batch)"
        print("Reject rate per batch and entity:")
        _frame(
            rt.warehouse.query(
                "SELECT q.batch_id, q.entity, q.checked_records AS input, q.failed_records AS rejected, "
                # PostgreSQL has no ROUND(double, int); NUMERIC works on both engines.
                "ROUND(CAST(100 * q.measured_value AS NUMERIC), 2) AS reject_pct, q.severity "
                "FROM fact_data_quality q "
                f"WHERE {batch_filter} AND q.rule_name = 'reject_rate' AND q.checked_records > 0 "
                "ORDER BY 1, 2",
                params,
            )
        )
        print("\nMost frequently failing rules:")
        _frame(
            rt.warehouse.query(
                "SELECT q.entity, q.rule_name, q.dimension, CAST(SUM(q.failed_records) AS BIGINT) AS failed "
                f"FROM fact_data_quality q WHERE {batch_filter} AND q.failed_records > 0 "
                "AND q.rule_name NOT IN ('reject_rate', 'reconciliation') "
                "GROUP BY 1, 2, 3 ORDER BY failed DESC, 1, 2",
                params,
            )
        )


def cmd_backfill(settings: Settings, args: argparse.Namespace) -> None:
    with pipeline.open_runtime(settings) as rt:
        _print([_summary(r) for r in pipeline.backfill(rt, args.start, args.end)])


def cmd_analytics(settings: Settings, args: argparse.Namespace) -> None:
    from finflow.analytics import lake

    for title, frame in lake.run_lake_queries(settings).items():
        print(f"\n== {title}")
        _frame(frame)


def cmd_benchmark(settings: Settings, args: argparse.Namespace) -> None:
    from finflow.analytics import benchmarks

    _print(benchmarks.run_all(settings))


def cmd_sql_examples(settings: Settings, args: argparse.Namespace) -> None:
    from finflow.analytics import sql_examples

    with pipeline.open_runtime(settings) as rt:
        for name, frame in sql_examples.run_examples(rt, verbose=args.verbose).items():
            print(f"{name}: {len(frame)} rows")
            if args.verbose:
                _frame(frame.head(10))


def cmd_serve_api(settings: Settings, args: argparse.Namespace) -> None:
    import os

    import uvicorn

    os.environ.setdefault("FINFLOW_LANDING_DIR", str(settings.landing_dir))
    uvicorn.run("finflow.sources.api:app", host=args.host, port=args.port, log_level="warning")


def _dir_size(path: Path) -> int:
    return sum(p.stat().st_size for p in path.rglob("*") if p.is_file()) if path.exists() else 0


def cmd_disk_usage(settings: Settings, args: argparse.Namespace) -> None:
    rows = {
        "landing (generated sources)": settings.landing_dir,
        "lake (bronze/silver/rejected/reports)": settings.lake_dir,
        "warehouse (DuckDB file)": settings.data_dir / "warehouse",
        "logs": settings.logs_dir,
        "source code (src, sql, tests)": None,
        "documentation (docs)": settings.home / "docs",
        ".venv (excluded from the 150 MB target)": settings.home / ".venv",
    }
    total = 0
    for label, path in rows.items():
        if path is None:
            size = sum(_dir_size(settings.home / d) for d in ("src", "sql", "tests", "airflow", "config"))
        else:
            size = _dir_size(path)
        if ".venv" not in label:
            total += size
        print(f"{label:45s} {size / 1_048_576:8.2f} MB")
    print(f"{'TOTAL (target < 150 MB, .venv excluded)':45s} {total / 1_048_576:8.2f} MB")


def cmd_clean_generated(settings: Settings, args: argparse.Namespace) -> None:
    """Delete generated artifacts only. Never touches source, docs or files outside data/."""
    data_dir = settings.data_dir.resolve()
    if data_dir == settings.home.resolve() or settings.home.resolve() not in data_dir.parents:
        raise FinFlowError(f"Refusing to clean {data_dir}: it must be a subdirectory of the project.")
    targets = [settings.landing_dir, settings.lake_dir, data_dir / "warehouse", settings.logs_dir]
    for target in targets:
        if target.exists():
            shutil.rmtree(target)
            print(f"removed {target}")
    if settings.s3 is not None:
        from finflow.common.storage import LakeStorage

        storage = LakeStorage.from_settings(settings)
        for prefix in ("bronze", "silver", "rejected", "reports"):
            storage.delete_dir(prefix)
        print(f"emptied bucket {settings.s3.bucket}")


def cmd_demo(settings: Settings, args: argparse.Namespace) -> None:
    """End-to-end walkthrough on the lightweight profile."""
    from finflow.warehouse import elt

    if not (settings.landing_dir / HISTORICAL_BATCH_ID).exists():
        cmd_generate(settings, argparse.Namespace(profile="small", force=False, error_rate=None))
    existing = len(list_landing_batches(settings.landing_dir)) - 1
    if existing < args.incremental:
        cmd_generate_incremental(settings, argparse.Namespace(count=args.incremental - existing, quiet=False))
    with pipeline.open_runtime(settings) as rt:
        print("\n### 1. ETL: process every pending batch")
        first = pipeline.run_pending(rt)
        _print([_summary(r) for r in first])
        before = rt.warehouse.query("SELECT COUNT(*) AS n, SUM(amount_minor) AS s FROM fact_transactions")
        print("\n### 2. Idempotency: force-reprocess the historical batch")
        pipeline.run_etl(rt, load_landing_batch(settings.landing_dir, HISTORICAL_BATCH_ID), force=True)
        after = rt.warehouse.query("SELECT COUNT(*) AS n, SUM(amount_minor) AS s FROM fact_transactions")
        print(
            f"fact_transactions before={int(before['n'].iloc[0])} after={int(after['n'].iloc[0])} "
            f"(sum {format_minor(int(before['s'].iloc[0]))} -> {format_minor(int(after['s'].iloc[0]))})"
        )
        print("\n### 3. ELT + marts + ETL/ELT reconciliation")
        for batch in list_landing_batches(settings.landing_dir):
            elt.run_elt(rt, batch)
        elt.refresh_marts(rt)
        mismatches = elt.reconcile(rt)
        print(f"days where ETL and ELT disagree: {len(mismatches)}")
        print("\n### 4. Daily volume (first 5 days)")
        _frame(
            rt.warehouse.query(
                "SELECT full_date, transactions, failed, failure_pct, gross_mxn_minor / 100 AS gross_mxn "
                "FROM mart_daily_transactions ORDER BY full_date LIMIT 5"
            )
        )
    cmd_status(settings, args)


# ---------------------------------------------------------------------- parser
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="finflow", description=__doc__)
    parser.add_argument(
        "--mode", choices=["lightweight", "data"], help="execution profile (default: FINFLOW_MODE)"
    )
    parser.add_argument("--log-level", help="override the configured log level")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("generate", help="generate the historical landing batch")
    p.add_argument("--profile", default="small", choices=["small", "medium", "large"])
    p.add_argument("--error-rate", type=float, help="override the share of corrupted transactions")
    p.add_argument("--force", action="store_true", help="delete existing landing data first")
    p.set_defaults(func=cmd_generate)

    p = sub.add_parser("generate-incremental", help="generate the next incremental day(s)")
    p.add_argument("--count", type=int, default=1)
    p.add_argument("--quiet", action="store_true", help="print only the new batch id")
    p.set_defaults(func=cmd_generate_incremental)

    p = sub.add_parser("seed", help="(data mode) write landing batches into the operational PostgreSQL")
    p.add_argument("--batch")
    p.set_defaults(func=cmd_seed)

    p = sub.add_parser("etl", help="run ingest -> transform -> load for pending batches")
    p.add_argument("--batch", help="process only this batch")
    p.add_argument("--force", action="store_true", help="reprocess even if already loaded")
    p.add_argument("--until", type=date.fromisoformat, help="stop after this business date")
    p.set_defaults(func=cmd_etl)

    p = sub.add_parser("step", help="run a single ETL step for a batch")
    p.add_argument("step", choices=["ingest", "validate", "transform", "load"])
    p.add_argument("--batch", required=True)
    p.set_defaults(func=cmd_step)

    p = sub.add_parser("elt", help="load raw transactions and transform them with SQL")
    p.add_argument("--batch")
    p.set_defaults(func=cmd_elt)

    sub.add_parser("marts", help="rebuild the analytical data marts").set_defaults(func=cmd_marts)
    sub.add_parser("status", help="batches, watermarks and row counts").set_defaults(func=cmd_status)

    p = sub.add_parser("quality-report", help="data quality summary from the warehouse")
    p.add_argument("--batch")
    p.set_defaults(func=cmd_quality_report)

    p = sub.add_parser("backfill", help="reprocess batches with business dates in a range")
    p.add_argument("--start", type=date.fromisoformat, required=True)
    p.add_argument("--end", type=date.fromisoformat, required=True)
    p.set_defaults(func=cmd_backfill)

    sub.add_parser("analytics", help="DuckDB queries directly on the Parquet lake").set_defaults(
        func=cmd_analytics
    )
    sub.add_parser("benchmark", help="small, reproducible performance comparisons").set_defaults(
        func=cmd_benchmark
    )

    p = sub.add_parser("sql-examples", help="execute every example in sql/examples")
    p.add_argument("--verbose", action="store_true")
    p.set_defaults(func=cmd_sql_examples)

    p = sub.add_parser("serve-api", help="run the FastAPI source simulator")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8000)
    p.set_defaults(func=cmd_serve_api)

    sub.add_parser("disk-usage", help="disk used by generated artifacts").set_defaults(func=cmd_disk_usage)
    sub.add_parser("clean-generated", help="delete generated data (never source code)").set_defaults(
        func=cmd_clean_generated
    )

    p = sub.add_parser("demo", help="end-to-end lightweight demonstration")
    p.add_argument("--incremental", type=int, default=2, help="incremental days to generate and process")
    p.set_defaults(func=cmd_demo)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        settings = load_settings(args.mode)
        configure_logging(
            args.log_level or settings.log_level,
            settings.logs_dir,
            settings.log_max_bytes,
            settings.log_backup_count,
        )
        args.func(settings, args)
    except QualityGateError as exc:
        print(f"QUALITY GATE FAILED: {exc}", file=sys.stderr)
        return 2
    except FinFlowError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
