"""Historical (initial) load: seed the operational source, then ingest,
validate, transform, load, run the ELT and refresh marts for the historical batch.

Trigger manually once after `make up-full` and `make generate-data`.
"""

from __future__ import annotations

from datetime import datetime

from airflow.sdk import DAG, Param, TaskGroup
from finflow_common import DEFAULT_ARGS, finflow_task

with DAG(
    dag_id="finflow_historical_ingestion",
    description="Initial load of the historical batch, end to end",
    start_date=datetime(2026, 1, 1),
    schedule=None,
    catchup=False,
    max_active_runs=1,
    default_args=DEFAULT_ARGS,
    params={
        "batch_id": Param("b000-historical", type="string"),
        "fail_at": Param("", type="string", description="ingest | transform | load to rehearse a failure"),
    },
    tags=["finflow", "etl"],
    doc_md=__doc__,
) as dag:
    batch = "{{ params.batch_id }}"

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

    seed >> etl >> analytics
