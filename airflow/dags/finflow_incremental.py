"""Daily incremental pipeline.

1. Simulate one more business day upstream (generator + operational writes).
2. Ingest only what changed since the watermarks, validate, transform, load.
3. Run the incremental ELT, refresh marts and publish the quality report.

The new batch id travels between tasks through XCom (a short string); data
never does — it moves through MinIO and PostgreSQL.
"""

from __future__ import annotations

from datetime import datetime

from airflow.sdk import DAG, Param, TaskGroup
from finflow_common import DEFAULT_ARGS, finflow_task

with DAG(
    dag_id="finflow_daily_incremental",
    description="Simulate a business day and process it incrementally",
    start_date=datetime(2026, 1, 1),
    schedule="@daily",
    catchup=False,  # the business calendar is simulated; never backfill wall-clock days
    max_active_runs=1,
    default_args=DEFAULT_ARGS,
    params={"fail_at": Param("", type="string", description="ingest | transform | load")},
    tags=["finflow", "etl", "incremental"],
    doc_md=__doc__,
) as dag:
    new_batch = finflow_task(
        "simulate_new_business_day",
        "generate-incremental --quiet",
        do_xcom_push=True,  # last stdout line = new batch id
        retries=0,  # generating twice would create two days
    )
    batch = "{{ ti.xcom_pull(task_ids='simulate_new_business_day') }}"
    seed = finflow_task("simulate_operational_writes", f"seed --batch {batch}")

    with TaskGroup("etl") as etl:
        ingest = finflow_task("ingest_to_bronze", f"step ingest --batch {batch}")
        validate = finflow_task("validate_data_quality", f"step validate --batch {batch}", retries=0)
        transform = finflow_task("transform_to_silver", f"step transform --batch {batch}")
        load = finflow_task("load_warehouse", f"step load --batch {batch}")
        ingest >> validate >> transform >> load

    with TaskGroup("analytics") as analytics:
        elt = finflow_task("elt_sql_transformations", f"elt --batch {batch}")
        report = finflow_task("data_quality_report", f"quality-report --batch {batch}")
        elt >> report

    new_batch >> seed >> etl >> analytics
