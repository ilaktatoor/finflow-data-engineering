"""Reprocess one batch or a date range from Bronze (no source access needed).

Use after fixing a transformation bug or after late-arriving reference data
(e.g. an account that was unknown when its transactions first arrived).
Triggering with a batch id replays that batch; with start/end dates it
backfills every batch whose business date falls in the range.
"""

from __future__ import annotations

from datetime import datetime

from airflow.sdk import DAG, Param
from finflow_common import DEFAULT_ARGS, finflow_task

with DAG(
    dag_id="finflow_reprocess",
    description="Replay batches from Bronze (reprocessing / backfill)",
    start_date=datetime(2026, 1, 1),
    schedule=None,
    catchup=False,
    max_active_runs=1,
    default_args=DEFAULT_ARGS,
    params={
        "start_date": Param("2026-01-30", type="string", format="date"),
        "end_date": Param("2026-01-31", type="string", format="date"),
        "fail_at": Param("", type="string"),
    },
    tags=["finflow", "backfill"],
    doc_md=__doc__,
) as dag:
    backfill = finflow_task(
        "backfill_from_bronze", "backfill --start {{ params.start_date }} --end {{ params.end_date }}"
    )
    marts = finflow_task("refresh_marts", "marts")
    report = finflow_task("data_quality_report", "quality-report")
    backfill >> marts >> report
