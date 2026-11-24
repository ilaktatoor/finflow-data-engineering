"""Shared settings for the FinFlow DAGs.

The DAGs only orchestrate. Every task calls the `finflow` CLI, so the logic
stays in the Python package (testable without Airflow) and Airflow adds
scheduling, retries, timeouts and logs. Nothing expensive happens at parse time.
"""

from __future__ import annotations

from datetime import timedelta

from airflow.providers.standard.operators.bash import BashOperator

FINFLOW = "/opt/airflow/finflow-venv/bin/finflow --mode data"

DEFAULT_ARGS = {
    "owner": "finflow",
    "retries": 2,
    "retry_delay": timedelta(seconds=30),
    "retry_exponential_backoff": True,
    "execution_timeout": timedelta(minutes=10),
}

# FINFLOW_RUN_ID ties every task of a DAG run to one FinFlow run id.
# FINFLOW_FAIL_AT lets a run rehearse failures: trigger with {"fail_at": "load"}.
TASK_ENV = {"FINFLOW_RUN_ID": "{{ run_id }}", "FINFLOW_FAIL_AT": "{{ params.fail_at }}"}


def finflow_task(task_id: str, command: str, **kwargs: object) -> BashOperator:
    """A task that runs one finflow CLI command. Exit code 2 = quality gate failed."""
    return BashOperator(
        task_id=task_id,
        bash_command=f"{FINFLOW} {command}",
        env=TASK_ENV,
        append_env=True,
        **kwargs,  # type: ignore[arg-type]
    )
