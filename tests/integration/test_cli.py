"""Smoke tests of the command line: the same commands the Makefile and Airflow run."""

from __future__ import annotations

import json
import shutil
from collections.abc import Iterator
from pathlib import Path

import pytest

from finflow.cli.main import main

pytestmark = pytest.mark.integration


@pytest.fixture
def workdir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    repo = Path(__file__).resolve().parents[2]
    monkeypatch.chdir(repo)  # FINFLOW_HOME defaults to the working directory
    monkeypatch.setenv("FINFLOW_DATA_DIR", str(repo / "data" / f"_pytest_{tmp_path.name}"))
    monkeypatch.setenv("FINFLOW_LOG_LEVEL", "WARNING")
    monkeypatch.delenv("FINFLOW_FAIL_AT", raising=False)
    data_dir = repo / "data" / f"_pytest_{tmp_path.name}"
    yield data_dir
    shutil.rmtree(data_dir, ignore_errors=True)


def test_demo_and_read_only_commands(workdir: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["demo", "--incremental", "1"]) == 0
    out = capsys.readouterr().out
    assert "days where ETL and ELT disagree: 0" in out
    assert "fact_transactions before=" in out

    for command in (
        ["status"],
        ["quality-report"],
        ["analytics"],
        ["sql-examples"],
        ["marts"],
        ["disk-usage"],
    ):
        assert main(command) == 0, command
    out = capsys.readouterr().out
    assert "Transaction volume by currency" in out
    assert "06_recursive_cte: " in out
    assert "TOTAL (target < 150 MB" in out

    assert main(["benchmark"]) == 0
    results = json.loads((workdir / "reports" / "benchmarks.json").read_text())
    assert results["vectorized_vs_row_by_row"]["rows"] > 2000


def test_individual_steps_and_backfill(workdir: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["generate"]) == 0
    assert main(["generate", "--profile", "small"]) == 1  # refuses to overwrite without --force
    for step in ("ingest", "validate", "transform", "load"):
        assert main(["step", step, "--batch", "b000-historical"]) == 0
    assert main(["generate-incremental", "--quiet"]) == 0
    assert capsys.readouterr().out.strip().endswith("b001-2026-01-31")
    assert main(["etl"]) == 0
    assert main(["backfill", "--start", "2026-01-30", "--end", "2026-01-31"]) == 0
    assert main(["etl", "--batch", "b001-2026-01-31"]) == 0  # already loaded: skipped
    assert '"status": "SKIPPED"' in capsys.readouterr().out


def test_quality_gate_exit_code(workdir: Path) -> None:
    assert main(["generate", "--error-rate", "0.3"]) == 0
    assert main(["etl"]) == 2
    assert main(["step", "validate", "--batch", "b000-historical"]) == 2


def test_clean_generated_only_removes_generated_data(workdir: Path) -> None:
    assert main(["generate"]) == 0
    assert main(["etl"]) == 0
    assert main(["clean-generated"]) == 0
    assert not (workdir / "landing").exists()
    assert not (workdir / "lake").exists()
    assert Path("src/finflow/cli/main.py").is_file()


def test_seed_requires_data_mode(workdir: Path) -> None:
    assert main(["seed"]) == 1
