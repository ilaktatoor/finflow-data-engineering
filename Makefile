# FinFlow developer commands. Every target is a thin wrapper around `uv run finflow ...`
# or `docker compose ...`; see docs/runbooks/local-setup.md for the raw commands.

UV      ?= uv
FINFLOW := $(UV) run finflow
DATA    := $(FINFLOW) --mode data
COMPOSE := docker compose

.DEFAULT_GOAL := help
.PHONY: help setup demo demo-incremental demo-quality-gate demo-failure generate-data pipeline incremental \
        elt marts quality-report status analytics benchmark sql-examples test test-unit test-integration \
        test-services coverage lint format typecheck check up-data up-full down logs seed demo-data \
        metabase-setup notebooks disk-usage clean-generated

help: ## List targets
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-20s %s\n", $$1, $$2}'

# ------------------------------------------------------------------ setup
setup: ## Create the virtualenv, install pinned deps and pre-commit hooks, create .env
	$(UV) sync --frozen
	@test -f .env || (cp .env.example .env && echo "created .env from .env.example")
	@-$(UV) run pre-commit install

# ------------------------------------------------- lightweight (no Docker)
demo: ## Full lightweight demo: generate, ETL, idempotent rerun, ELT, marts, status
	$(FINFLOW) demo

demo-incremental: ## Generate and process one more business day
	$(FINFLOW) generate-incremental
	$(FINFLOW) etl
	$(FINFLOW) elt

demo-quality-gate: ## Show the pipeline refusing a batch with 30% bad records (separate data dir)
	FINFLOW_DATA_DIR=data/_quality_gate $(FINFLOW) generate --error-rate 0.30 --force
	-FINFLOW_DATA_DIR=data/_quality_gate $(FINFLOW) etl
	FINFLOW_DATA_DIR=data/_quality_gate $(FINFLOW) quality-report

demo-failure: ## Rehearse a failure in the load step and the recovery (separate data dir)
	FINFLOW_DATA_DIR=data/_failure_drill $(FINFLOW) generate --force
	-FINFLOW_DATA_DIR=data/_failure_drill FINFLOW_FAIL_AT=load $(FINFLOW) etl
	FINFLOW_DATA_DIR=data/_failure_drill $(FINFLOW) status
	FINFLOW_DATA_DIR=data/_failure_drill $(FINFLOW) etl
	FINFLOW_DATA_DIR=data/_failure_drill $(FINFLOW) status

generate-data: ## Generate the historical batch (PROFILE=small|medium|large)
	$(FINFLOW) generate --profile $(or $(PROFILE),small)

pipeline: ## Run the ETL for every pending batch
	$(FINFLOW) etl

incremental: ## Generate the next business day and run ETL on it
	$(FINFLOW) generate-incremental
	$(FINFLOW) etl

elt: ## Run the SQL ELT path, rebuild marts, reconcile with the ETL
	$(FINFLOW) elt

marts: ## Rebuild the data marts
	$(FINFLOW) marts

quality-report: ## Data quality summary
	$(FINFLOW) quality-report

status: ## Batches, watermarks and row counts
	$(FINFLOW) status

analytics: ## DuckDB queries directly on the Parquet lake
	$(FINFLOW) analytics

benchmark: ## Reproducible small-scale performance comparisons
	$(FINFLOW) benchmark

sql-examples: ## Execute every example in sql/examples (rolled back)
	$(FINFLOW) sql-examples

# ------------------------------------------------------------------ quality
test: ## Unit + contract + lightweight integration tests (no Docker)
	$(UV) run pytest -m "not services"

test-unit: ## Unit and contract tests only
	$(UV) run pytest tests/unit tests/contracts

test-integration: ## Lightweight end-to-end tests (DuckDB + local files)
	$(UV) run pytest -m integration

test-services: ## Tests against the Docker data services (run `make up-data` first)
	FINFLOW_TEST_SERVICES=1 $(UV) run pytest -m services

coverage: ## Tests with a coverage report
	$(UV) run pytest -m "not services" --cov --cov-report=term --cov-report=xml

lint: ## Ruff lint + format check
	$(UV) run ruff check src tests airflow scripts
	$(UV) run ruff format --check src tests airflow scripts

format: ## Apply ruff formatting and safe fixes
	$(UV) run ruff format src tests airflow scripts
	$(UV) run ruff check --fix src tests airflow scripts

typecheck: ## mypy
	$(UV) run mypy

check: lint typecheck test ## Everything CI runs

# ------------------------------------------------------- Docker profiles
up-data: ## Start PostgreSQL x2, MinIO and the FastAPI source simulator
	@test -f .env || (echo "run 'make setup' first" && exit 1)
	@mkdir -p data/landing
	$(COMPOSE) --profile data up -d --build --wait

up-full: ## up-data + Airflow + Metabase (needs ~4 GB free RAM)
	@test -f .env || (echo "run 'make setup' first" && exit 1)
	@mkdir -p data/landing airflow/logs
	$(COMPOSE) --profile full up -d --build --wait

down: ## Stop all containers (volumes are kept; add V=1 to delete them)
	$(COMPOSE) --profile full down $(if $(V),-v,)

logs: ## Follow container logs (SERVICE=name for one service)
	$(COMPOSE) --profile full logs -f --tail=100 $(SERVICE)

seed: ## (data) Write landing batches into the operational PostgreSQL
	$(DATA) seed

demo-data: ## Data-profile demo: same pipeline on MinIO + PostgreSQL + API
	@test -d data/landing/b000-historical || $(FINFLOW) generate
	$(DATA) seed --batch b000-historical
	$(DATA) etl --batch b000-historical
	$(FINFLOW) generate-incremental
	$(DATA) seed
	$(DATA) etl
	$(DATA) elt
	$(DATA) status

metabase-setup: ## Create the Metabase admin, warehouse connection and dashboard
	$(UV) run python scripts/metabase_setup.py

notebooks: ## Start JupyterLab with the notebook dependencies
	$(UV) run --group notebooks jupyter lab notebooks/

# ------------------------------------------------------------ housekeeping
disk-usage: ## Disk used by generated data, code, docs and the venv
	$(FINFLOW) disk-usage

clean-generated: ## Delete generated data, lake, warehouse and logs (never code or docs)
	$(FINFLOW) clean-generated
	rm -rf data/_quality_gate data/_failure_drill data/reports
