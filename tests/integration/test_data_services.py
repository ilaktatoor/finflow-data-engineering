"""Data-profile tests against the Docker services (PostgreSQL x2, MinIO, FastAPI).

Opt-in: `make up-data && make test-services` (sets FINFLOW_TEST_SERVICES=1).
Each run creates its own databases and bucket and drops them afterwards, so it
never touches data you created with `make demo-data`. The API simulator runs
in-process on a free port, pointed at a temporary landing zone; the container's
API is only health-checked.
"""

from __future__ import annotations

import json
import os
import socket
import threading
import time
import uuid
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest
import sqlalchemy as sa
import uvicorn

from finflow.common.config import Settings, load_settings, read_env_file
from finflow.common.storage import LakeStorage
from finflow.generators.synthetic import HISTORICAL_BATCH_ID, SyntheticGenerator, write_batch
from finflow.orchestration import pipeline
from finflow.sources.models import load_landing_batch
from finflow.sources.operational import seed_batch
from finflow.warehouse import elt

REPO_ROOT = Path(__file__).resolve().parents[2]
pytestmark = [
    pytest.mark.services,
    pytest.mark.skipif(not os.environ.get("FINFLOW_TEST_SERVICES"), reason="set FINFLOW_TEST_SERVICES=1"),
]


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _with_database(url: str, name: str) -> str:
    # str(URL) masks the password as "***"; render it explicitly.
    return sa.make_url(url).set(database=name).render_as_string(hide_password=False)


@pytest.fixture(scope="module")
def services(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Settings]:
    env = {**read_env_file(REPO_ROOT / ".env"), **os.environ}
    suffix = uuid.uuid4().hex[:8]
    test_dbs = {"FINFLOW_WAREHOUSE_URL": f"wh_test_{suffix}", "FINFLOW_OPS_DB_URL": f"ops_test_{suffix}"}
    admin_engines = {key: sa.create_engine(env[key], isolation_level="AUTOCOMMIT") for key in test_dbs}
    for key, name in test_dbs.items():
        with admin_engines[key].connect() as conn:
            conn.exec_driver_sql(f'CREATE DATABASE "{name}"')

    data_dir = tmp_path_factory.mktemp("services")
    landing = data_dir / "landing"
    landing.mkdir()
    port = _free_port()
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setenv("FINFLOW_LANDING_DIR", str(landing))
    server = uvicorn.Server(
        uvicorn.Config("finflow.sources.api:app", host="127.0.0.1", port=port, log_level="warning")
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    while not server.started:
        time.sleep(0.05)

    monkeypatch.setenv("FINFLOW_DATA_DIR", str(data_dir))
    monkeypatch.setenv("FINFLOW_S3_BUCKET", f"finflow-test-{suffix}")
    monkeypatch.setenv("FINFLOW_SOURCE_API_URL", f"http://127.0.0.1:{port}")
    for key, name in test_dbs.items():
        monkeypatch.setenv(key, _with_database(env[key], name))
    try:
        yield load_settings("data", home=REPO_ROOT)
    finally:
        server.should_exit = True
        thread.join(timeout=5)
        settings = load_settings("data", home=REPO_ROOT)
        storage = LakeStorage.from_settings(settings)
        storage.fs.delete_dir(storage.root)
        monkeypatch.undo()
        for key, name in test_dbs.items():
            with admin_engines[key].connect() as conn:
                conn.exec_driver_sql(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
            admin_engines[key].dispose()


def _seed(settings: Settings, batch_id: str) -> None:
    assert settings.ops_db_url
    batch = load_landing_batch(settings.landing_dir, batch_id)
    seed_batch(
        settings.ops_db_url, settings.landing_dir, batch, settings.sql_dir / "operational" / "schema.sql"
    )


def test_container_api_is_healthy() -> None:
    assert httpx.get("http://127.0.0.1:8000/health", timeout=5).json() == {"status": "ok"}


def test_full_data_profile_flow(services: Settings) -> None:
    settings = services
    generator = SyntheticGenerator(settings.generation)
    write_batch(generator.historical_batch(), settings.landing_dir, "small", 42)
    _seed(settings, HISTORICAL_BATCH_ID)

    with pipeline.open_runtime(settings) as rt:
        assert rt.warehouse.dialect == "postgres"
        pipeline.run_pending(rt)
        q = rt.warehouse.query
        assert q("SELECT COUNT(*) AS n FROM fact_transactions")["n"].iloc[0] == 1910

        # Each entity came from the source system the data profile assigns to it.
        bronze = rt.storage.list_files("bronze/")
        assert any("source=core_banking_db/entity=customers" in f for f in bronze)
        assert any("source=lending_db/entity=loan_payments" in f for f in bronze)
        assert any("source=rates_api/entity=exchange_rates" in f for f in bronze)
        assert any("source=merchant_api/entity=merchants" in f for f in bronze)
        assert any("source=transaction_files/entity=transactions" in f for f in bronze)

        # Incremental day: the database and API extractions only return changes.
        write_batch(generator.incremental_batch(1), settings.landing_dir, "small", 42)
        _seed(settings, "b001-2026-01-31")
        pipeline.run_pending(rt)
        marker = rt.storage.read_bytes("bronze/_batches/batch_id=b001-2026-01-31.json")
        counts = {o["entity"]: o["record_count"] for o in json.loads(marker)["objects"]}
        assert counts["customers"] == 3  # only the changed customers, via the updated_at watermark
        assert counts["exchange_rates"] == 3  # only the new day, via the API date window
        assert "merchants" not in counts  # nothing changed upstream
        assert q("SELECT COUNT(*) AS n FROM dim_customer WHERE NOT is_current")["n"].iloc[0] == 3

        # Idempotency on PostgreSQL.
        before = q("SELECT COUNT(*) AS n, SUM(amount_minor) AS s FROM fact_transactions").iloc[0].tolist()
        pipeline.run_etl(rt, load_landing_batch(settings.landing_dir, HISTORICAL_BATCH_ID), force=True)
        after = q("SELECT COUNT(*) AS n, SUM(amount_minor) AS s FROM fact_transactions").iloc[0].tolist()
        assert before == after

        # ELT on PostgreSQL reconciles with the ETL star schema.
        for batch_id in (HISTORICAL_BATCH_ID, "b001-2026-01-31"):
            elt.run_elt(rt, load_landing_batch(settings.landing_dir, batch_id))
        elt.refresh_marts(rt)
        assert elt.reconcile(rt).empty

        # The SQL examples, including the PostgreSQL-only materialized view, run.
        from finflow.analytics.sql_examples import run_examples

        results = run_examples(rt)
        assert "16_materialized_view.postgres" in results
        assert len(results["16_materialized_view.postgres"]) > 0

    # DuckDB reads the Parquet lake straight from MinIO.
    from finflow.analytics.lake import run_lake_queries

    lake = run_lake_queries(settings)
    assert len(lake["Transaction volume by currency"]) == 4
