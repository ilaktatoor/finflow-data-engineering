# Local setup

## Requirements

| | Minimum | Recommended | Measured on the build machine |
|---|---|---|---|
| Lightweight profile | 2 CPU, 2 GB RAM, 1.5 GB disk | 4 CPU, 4 GB RAM | demo peak RSS 504–559 MiB, 7 s |
| Data profile (+ PostgreSQL ×2, MinIO, API) | 4 GB RAM, 4 GB disk | 8 GB RAM | containers ~0.5 GB RAM; `make demo-data` 29.9 s |
| Full platform (+ Airflow, Metabase) | 8 GB RAM, 10 GB disk | 16 GB RAM | 6 containers ~2–2.8 GB RAM; images 7.3 GB (Airflow image 3.8 GB) |

Disk: the virtualenv is ~590 MB; generated data for the default demo is
under 30 MB (`make disk-usage`). Docker images (PostgreSQL, MinIO, Airflow,
Metabase, the app image) add a few GB.

Software: Linux or macOS (Windows through WSL2), `git`, `make` (optional),
[uv](https://docs.astral.sh/uv/) ≥ 0.13 (installs Python 3.12 for you), and
Docker with Compose v2 for the data/full profiles. Your user needs access to
the Docker socket (on Linux: `sudo usermod -aG docker $USER`, then log out and
in; `newgrp docker` works for the current shell).

## Lightweight profile (no Docker)

```bash
git clone <your-fork-url> finflow-data-engineering
cd finflow-data-engineering
make setup        # uv sync --frozen; cp .env.example .env; pre-commit install
make demo         # generate, ETL, idempotent rerun, ELT, marts, status
make test         # unit + contract + lightweight integration tests
```

Without Make:

```bash
uv sync --frozen
cp .env.example .env
uv run finflow demo
uv run pytest -m "not services"
```

`.env` is optional in this profile; `FINFLOW_MODE=lightweight` is the default.

## Data profile

```bash
make up-data      # docker compose --profile data up -d --build --wait
make demo-data    # generate (if needed), seed the operational DB, ETL, incremental, ELT
make test-services
```

Without Make:

```bash
docker compose --profile data up -d --build --wait
uv run finflow generate
uv run finflow --mode data seed --batch b000-historical
uv run finflow --mode data etl
```

The host CLI reaches the containers through `127.0.0.1` ports configured in
`.env` (`FINFLOW_*` variables). Service URLs:

| Service | URL / port | Credentials (local placeholders from .env) |
|---|---|---|
| MinIO console | http://127.0.0.1:9001 | `MINIO_ROOT_USER` / `MINIO_ROOT_PASSWORD` |
| MinIO S3 API | http://127.0.0.1:9000 | same |
| Source API | http://127.0.0.1:8000/docs | none |
| Operational PostgreSQL | 127.0.0.1:5433, db `operational` | `OPS_DB_USER` / `OPS_DB_PASSWORD` |
| Warehouse PostgreSQL | 127.0.0.1:5434, db `warehouse` | `WAREHOUSE_DB_USER` / `WAREHOUSE_DB_PASSWORD` |

## Full platform

```bash
echo "AIRFLOW_UID=$(id -u)" >> .env   # files Airflow writes under ./data stay yours
make up-full
make metabase-setup                   # admin user, warehouse connection, dashboard
```

| Service | URL | Login |
|---|---|---|
| Airflow | http://127.0.0.1:8080 | `admin` / `AIRFLOW_ADMIN_PASSWORD` |
| Metabase | http://127.0.0.1:3000 | `METABASE_ADMIN_EMAIL` / `METABASE_ADMIN_PASSWORD` |

DAGs start paused. If you already ran `make demo-data`, the historical batch
is loaded; otherwise trigger `finflow_historical_ingestion` first.

Unpausing `finflow_daily_incremental` (a `@daily` DAG) makes the scheduler
create a run for the latest interval immediately, so unpause + a manual
trigger simulates **two** business days. That is standard Airflow behaviour.

## Notebooks

```bash
make notebooks     # uv run --group notebooks jupyter lab notebooks/
```

The notebooks read `data/` and expect `make demo` to have run. Any Jupyter
installation works as long as it uses the project's virtualenv as kernel.

## Stopping and cleaning

```bash
make down              # stop containers, keep volumes
make down V=1          # also delete database and MinIO volumes
make clean-generated   # delete data/landing, data/lake, warehouse file, logs
```

`clean-generated` refuses to run if `FINFLOW_DATA_DIR` points outside the
project, and never touches source code or documentation.
