#!/bin/sh
# Runs once, on first start of the warehouse-db container (empty volume).
# Creates the Airflow and Metabase metadata databases and a read-only role for
# BI tools. All passwords come from the environment (.env), never from this file.
set -eu

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<SQL
CREATE ROLE airflow LOGIN PASSWORD '${AIRFLOW_DB_PASSWORD}';
CREATE DATABASE airflow OWNER airflow;
CREATE ROLE metabase LOGIN PASSWORD '${METABASE_DB_PASSWORD}';
CREATE DATABASE metabase OWNER metabase;

-- Least privilege for dashboards: read-only access to warehouse tables,
-- including tables the pipeline creates later.
CREATE ROLE analytics_reader LOGIN PASSWORD '${ANALYTICS_READER_PASSWORD}';
GRANT CONNECT ON DATABASE ${POSTGRES_DB} TO analytics_reader;
GRANT USAGE ON SCHEMA public TO analytics_reader;
ALTER DEFAULT PRIVILEGES FOR ROLE ${POSTGRES_USER} IN SCHEMA public GRANT SELECT ON TABLES TO analytics_reader;
SQL
