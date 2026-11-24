# Airflow with FinFlow installed in its own virtual environment.
# Airflow's constraints and FinFlow's pins (pandas 3, SQLAlchemy 2.1) cannot share
# one environment, so DAG tasks call /opt/airflow/finflow-venv/bin/finflow.
FROM apache/airflow:3.4.0-python3.12

COPY --from=ghcr.io/astral-sh/uv:0.13.6 /uv /usr/local/bin/uv

USER root
RUN mkdir -p /opt/finflow && chown airflow:0 /opt/finflow
USER airflow

WORKDIR /opt/finflow
COPY --chown=airflow:0 pyproject.toml uv.lock README.md ./
RUN uv venv --python /usr/local/bin/python /opt/airflow/finflow-venv \
    && uv export --frozen --no-dev --no-emit-project --format requirements.txt -o /tmp/requirements.txt \
    && VIRTUAL_ENV=/opt/airflow/finflow-venv uv pip install --no-cache -r /tmp/requirements.txt
COPY --chown=airflow:0 src ./src
COPY --chown=airflow:0 sql ./sql
COPY --chown=airflow:0 config ./config
RUN VIRTUAL_ENV=/opt/airflow/finflow-venv uv pip install --no-cache --no-deps .

WORKDIR /opt/airflow
