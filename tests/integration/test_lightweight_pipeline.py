"""End-to-end tests of the lightweight profile: local filesystem lake + DuckDB.

No Docker needed. One module-scoped run generates the small profile plus two
incremental days and processes them; each test then inspects a different
guarantee. Tests that mutate state build their own isolated run.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from finflow.common.config import Settings, load_settings
from finflow.common.errors import QualityGateError, SimulatedFailure
from finflow.generators.synthetic import HISTORICAL_BATCH_ID, SyntheticGenerator, write_batch
from finflow.orchestration import pipeline
from finflow.sources.models import load_landing_batch
from finflow.warehouse import elt

pytestmark = pytest.mark.integration
REPO_ROOT = Path(__file__).resolve().parents[2]


def make_settings(
    data_dir: Path, monkeypatch: pytest.MonkeyPatch, error_rate: float | None = None
) -> Settings:
    monkeypatch.setenv("FINFLOW_DATA_DIR", str(data_dir))
    monkeypatch.delenv("FINFLOW_FAIL_AT", raising=False)
    settings = load_settings("lightweight", home=REPO_ROOT)
    config = settings.generation
    if error_rate is not None:
        from dataclasses import replace

        config = replace(config, error_rate=error_rate)
    generator = SyntheticGenerator(config)
    write_batch(generator.historical_batch(), settings.landing_dir, "small", config.seed)
    return settings


def reports(settings: Settings) -> dict[str, Any]:
    return {
        p.parent.name: json.loads(p.read_text())
        for p in settings.landing_dir.glob("*/_generation_report.json")
    }


@pytest.fixture(scope="module")
def loaded(tmp_path_factory: pytest.TempPathFactory) -> Iterator[tuple[Settings, pipeline.Runtime]]:
    monkeypatch = pytest.MonkeyPatch()
    settings = make_settings(tmp_path_factory.mktemp("lw"), monkeypatch)
    generator = SyntheticGenerator(settings.generation)
    for sequence in (1, 2):
        write_batch(generator.incremental_batch(sequence), settings.landing_dir, "small", 42)
    with pipeline.open_runtime(settings) as rt:
        pipeline.run_pending(rt)
        for batch in pipeline.resolve_batches(settings, None):
            elt.run_elt(rt, batch)
        elt.refresh_marts(rt)
        yield settings, rt
    monkeypatch.undo()


def scalar(rt: pipeline.Runtime, sql: str) -> Any:
    return rt.warehouse.query(sql).iloc[0, 0]


def test_historical_counts_match_generator_report(loaded: tuple[Settings, pipeline.Runtime]) -> None:
    settings, rt = loaded
    expected = reports(settings)[HISTORICAL_BATCH_ID]["expected"]
    row = rt.warehouse.query(
        "SELECT checked_records, failed_records FROM fact_data_quality "
        f"WHERE batch_id = '{HISTORICAL_BATCH_ID}' AND entity = 'transactions' AND rule_name = 'reject_rate'"
    ).iloc[0]
    assert row["failed_records"] == expected["transactions_rejected"]
    dupes = scalar(
        rt,
        "SELECT failed_records FROM fact_data_quality WHERE entity = 'transactions' "
        f"AND rule_name = 'duplicate' AND batch_id = '{HISTORICAL_BATCH_ID}'",
    )
    assert dupes == expected["transactions_duplicates"]


def test_every_batch_reconciles_input_with_outputs(loaded: tuple[Settings, pipeline.Runtime]) -> None:
    settings, rt = loaded
    for batch_id, report in reports(settings).items():
        quality = json.loads(rt.storage.read_bytes(f"reports/quality/{batch_id}/report.json"))
        txn = quality["entities"]["transactions"]
        assert txn["input"] == txn["accepted"] + txn["rejected"] + txn["duplicates"]
        assert txn["input"] == report["record_counts"]["transactions"]
        assert txn["rejected"] == report["expected"]["transactions_rejected"]


def test_rejected_records_are_isolated_with_payload(loaded: tuple[Settings, pipeline.Runtime]) -> None:
    _, rt = loaded
    files = rt.storage.list_files("rejected/transactions/")
    quarantine = rt.storage.read_parquet(files)
    assert set(quarantine["disposition"]) == {"rejected", "duplicate"}
    assert quarantine["raw_record"].str.startswith("{").all()
    rejected_ids = set(quarantine.loc[quarantine["disposition"] == "rejected", "natural_key"].dropna())
    loaded_ids = set(rt.warehouse.query("SELECT transaction_id FROM fact_transactions")["transaction_id"])
    # A rejected id may only be in the warehouse if a later batch re-sent it validly.
    assert len(rejected_ids & loaded_ids) <= 2


def test_bronze_and_silver_layout(loaded: tuple[Settings, pipeline.Runtime]) -> None:
    _, rt = loaded
    bronze_files = rt.storage.list_files("bronze/")
    assert any(
        "source=transaction_files/entity=transactions/batch_date=2026-01-30" in f for f in bronze_files
    )
    assert sum(f.endswith("_manifest.json") for f in bronze_files) == 8 + 4 + 4
    silver_days = {f.split("/")[2] for f in rt.storage.list_files("silver/transactions/")}
    assert "txn_date=2026-01-01" in silver_days and "txn_date=2026-02-01" in silver_days


def test_scd2_versions_are_consistent(loaded: tuple[Settings, pipeline.Runtime]) -> None:
    _, rt = loaded
    assert scalar(rt, "SELECT COUNT(*) FROM dim_customer") == 100 + 3 + 3
    assert scalar(rt, "SELECT COUNT(*) FROM dim_customer WHERE is_current") == 100
    overlaps = scalar(
        rt,
        """
        SELECT COUNT(*) FROM dim_customer a JOIN dim_customer b
          ON a.customer_id = b.customer_id AND a.customer_key < b.customer_key
         AND a.valid_from < COALESCE(b.valid_to, TIMESTAMP '9999-12-31')
         AND b.valid_from < COALESCE(a.valid_to, TIMESTAMP '9999-12-31')""",
    )
    assert overlaps == 0


def test_facts_point_to_the_customer_version_valid_at_event_time(
    loaded: tuple[Settings, pipeline.Runtime],
) -> None:
    _, rt = loaded
    wrong = scalar(
        rt,
        """
        SELECT COUNT(*) FROM fact_transactions f JOIN dim_customer c ON c.customer_key = f.customer_key
        WHERE NOT (f.event_ts >= c.valid_from AND (c.valid_to IS NULL OR f.event_ts < c.valid_to))""",
    )
    assert wrong == 0
    historical_links = scalar(
        rt,
        """
        SELECT COUNT(*) FROM fact_transactions f JOIN dim_customer c ON c.customer_key = f.customer_key
        WHERE NOT c.is_current""",
    )
    assert historical_links > 0  # older facts keep the old version of changed customers


def test_status_corrections_and_late_arrivals(loaded: tuple[Settings, pipeline.Runtime]) -> None:
    settings, rt = loaded
    batch = load_landing_batch(settings.landing_dir, "b001-2026-01-31")
    corrections = [
        json.loads(line)
        for line in (settings.landing_dir / batch.batch_id / "transactions.jsonl").read_text().splitlines()
        if line.startswith('{"transaction_id": "T000')
    ]
    ids = ", ".join(f"'{c['transaction_id']}'" for c in corrections)
    statuses = rt.warehouse.query(
        f"SELECT status, batch_id FROM fact_transactions WHERE transaction_id IN ({ids})"
    )
    assert len(statuses) == len(corrections)
    assert set(statuses["status"]) == {"COMPLETED"}
    late = scalar(rt, "SELECT COUNT(*) FROM fact_transactions WHERE is_late_arriving")
    expected_late = sum(
        r["expected"]["late_arriving"] + r["expected"]["status_corrections"]
        for r in reports(settings).values()
    )
    assert late == expected_late


def test_watermarks_advance_to_last_window(loaded: tuple[Settings, pipeline.Runtime]) -> None:
    _, rt = loaded
    assert str(scalar(rt, "SELECT watermark_ts FROM etl_watermark WHERE entity = 'transactions'")).startswith(
        "2026-02-02"
    )
    assert str(scalar(rt, "SELECT watermark_ts FROM etl_watermark WHERE entity = 'merchants'")).startswith(
        "2026-01-31"
    )


def test_etl_and_elt_reconcile(loaded: tuple[Settings, pipeline.Runtime]) -> None:
    _, rt = loaded
    assert elt.reconcile(rt).empty
    assert scalar(rt, "SELECT COUNT(*) FROM elt_transactions") == scalar(
        rt, "SELECT COUNT(*) FROM fact_transactions"
    )


def test_marts_answer_business_questions(loaded: tuple[Settings, pipeline.Runtime]) -> None:
    _, rt = loaded
    daily = rt.warehouse.query("SELECT * FROM mart_daily_transactions")
    assert daily["transactions"].sum() == scalar(rt, "SELECT COUNT(*) FROM fact_transactions")
    share = scalar(rt, "SELECT SUM(share_pct) FROM mart_currency_distribution")
    assert 99.9 <= float(share) <= 100.1
    assert scalar(rt, "SELECT COUNT(*) FROM mart_customer_activity WHERE activity_rank = 1") >= 1
    assert scalar(rt, "SELECT COUNT(*) FROM mart_risk_flags") > 0


def test_forced_rerun_is_idempotent(loaded: tuple[Settings, pipeline.Runtime]) -> None:
    settings, rt = loaded
    snapshot = (
        "SELECT (SELECT COUNT(*) FROM fact_transactions) AS facts, "
        "(SELECT SUM(amount_minor) FROM fact_transactions) AS amount, "
        "(SELECT COUNT(*) FROM dim_customer) AS customers, "
        "(SELECT COUNT(*) FROM fact_data_quality) AS dq, "
        "(SELECT COUNT(*) FROM fact_loan_payments) AS payments"
    )
    before = rt.warehouse.query(snapshot).iloc[0].to_dict()
    for batch in pipeline.resolve_batches(settings, None):
        pipeline.run_etl(rt, batch, force=True)
        elt.run_elt(rt, batch)
    after = rt.warehouse.query(snapshot).iloc[0].to_dict()
    assert before == after
    assert elt.reconcile(rt).empty


def test_failure_rolls_back_and_recovers(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    settings = make_settings(tmp_path, monkeypatch)
    batch = load_landing_batch(settings.landing_dir, HISTORICAL_BATCH_ID)
    with pipeline.open_runtime(settings) as rt:
        monkeypatch.setenv("FINFLOW_FAIL_AT", "load")
        with pytest.raises(SimulatedFailure):
            pipeline.run_etl(rt, batch)
        assert scalar(rt, "SELECT COUNT(*) FROM fact_transactions") == 0
        assert scalar(rt, "SELECT COUNT(*) FROM etl_watermark") == 0  # never advanced
        assert pipeline.batch_statuses(rt)[batch.batch_id] == "FAILED"

        monkeypatch.delenv("FINFLOW_FAIL_AT")
        pipeline.run_pending(rt)
        assert scalar(rt, "SELECT COUNT(*) FROM fact_transactions") == 1910
        steps = rt.warehouse.query("SELECT step, status FROM fact_pipeline_execution ORDER BY execution_id")
        assert ("load", "FAILED") in set(map(tuple, steps.to_numpy()))


def test_quality_gate_blocks_the_batch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    settings = make_settings(tmp_path, monkeypatch, error_rate=0.3)
    with pipeline.open_runtime(settings) as rt:
        with pytest.raises(QualityGateError, match="exceeds the critical threshold"):
            pipeline.run_pending(rt)
        assert scalar(rt, "SELECT COUNT(*) FROM fact_transactions") == 0
        assert scalar(rt, "SELECT COUNT(*) FROM dim_customer") == 0
        assert rt.storage.list_files("silver/") == []  # nothing reached Silver
        assert rt.storage.list_files("rejected/transactions/")  # but the evidence is kept
        assert pipeline.batch_statuses(rt)[HISTORICAL_BATCH_ID] == "QUALITY_FAILED"
        assert scalar(rt, "SELECT COUNT(*) FROM fact_data_quality WHERE severity = 'critical'") == 1


def test_replay_from_bronze_after_source_disappears(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    settings = make_settings(tmp_path, monkeypatch)
    batch = load_landing_batch(settings.landing_dir, HISTORICAL_BATCH_ID)
    with pipeline.open_runtime(settings) as rt:
        pipeline.ingest(rt, batch)
        for path in (settings.landing_dir / HISTORICAL_BATCH_ID).glob("*.*sv"):
            path.unlink()  # the CSV exports are gone upstream
        (settings.landing_dir / HISTORICAL_BATCH_ID / "transactions.jsonl").unlink()
        pipeline.transform(rt, batch)
        pipeline.load(rt, batch)
        assert scalar(rt, "SELECT COUNT(*) FROM fact_transactions") == 1910


def test_reconciliation_guard_catches_lost_rows(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    settings = make_settings(tmp_path, monkeypatch)
    batch = load_landing_batch(settings.landing_dir, HISTORICAL_BATCH_ID)
    with pipeline.open_runtime(settings) as rt:
        pipeline.ingest(rt, batch)
        pipeline.transform(rt, batch)
        # Sabotage the load script so one dimension join silently drops every FEE.
        original = pipeline.LOAD_SCRIPTS["transactions"]
        sabotaged = tmp_path / "sabotaged.sql"
        sql = (settings.sql_dir / "warehouse" / original).read_text()
        sabotaged.write_text(
            sql.replace(
                "JOIN dim_transaction_type t ON t.code = s.transaction_type",
                "JOIN dim_transaction_type t ON t.code = s.transaction_type AND t.code <> 'FEE'",
            )
        )
        monkeypatch.setitem(pipeline.LOAD_SCRIPTS, "transactions", str(sabotaged))
        with pytest.raises(pipeline.ReconciliationError, match="fact_transactions"):
            pipeline.load(rt, batch)
        assert scalar(rt, "SELECT COUNT(*) FROM fact_transactions") == 0


def test_point_in_time_guard_catches_wrong_customer_version(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Counts and sums cannot detect facts linked to the wrong SCD2 version; this guard does."""
    settings = make_settings(tmp_path, monkeypatch)
    generator = SyntheticGenerator(settings.generation)
    for sequence in (1, 2):
        write_batch(generator.incremental_batch(sequence), settings.landing_dir, "small", 42)
    sql = (settings.sql_dir / "warehouse" / pipeline.LOAD_SCRIPTS["transactions"]).read_text()
    broken = sql.replace(
        " AND s.event_ts >= c.valid_from\n AND (c.valid_to IS NULL OR s.event_ts < c.valid_to)\n", "\n", 1
    )
    assert broken != sql
    sabotaged = tmp_path / "no_validity.sql"
    sabotaged.write_text(broken)
    monkeypatch.setitem(pipeline.LOAD_SCRIPTS, "transactions", str(sabotaged))
    with (
        pipeline.open_runtime(settings) as rt,
        pytest.raises(pipeline.ReconciliationError, match="not valid"),
    ):
        pipeline.run_pending(rt)
