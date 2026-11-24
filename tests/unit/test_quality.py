from collections import Counter
from datetime import datetime

import pandas as pd

from finflow.common.config import Settings
from finflow.transformations.silver import EntityResult
from finflow.validation.quality import evaluate, rule_dimension


def result(input_count: int, rejected: int, duplicates: int = 0) -> EntityResult:
    quarantine = pd.DataFrame({"disposition": ["rejected"] * rejected + ["duplicate"] * duplicates})
    accepted = pd.DataFrame({"x": range(input_count - rejected - duplicates)})
    return EntityResult("transactions", accepted, quarantine, input_count, Counter({"status:isin": rejected}))


def test_gate_passes_below_threshold(settings: Settings) -> None:
    rows, critical, report = evaluate([result(100, 5)], settings.quality, "b", "r", datetime(2026, 1, 1))
    assert critical == [] and report["status"] == "passed"
    gate = rows[rows["rule_name"] == "reject_rate"].iloc[0]
    assert gate["severity"] == "warning" and gate["measured_value"] == 0.05


def test_gate_fails_above_critical_threshold(settings: Settings) -> None:
    _, critical, report = evaluate([result(100, 11)], settings.quality, "b", "r", datetime(2026, 1, 1))
    assert report["status"] == "failed"
    assert "exceeds the critical threshold" in critical[0]


def test_reconciliation_failure_is_critical(settings: Settings) -> None:
    broken = result(100, 5)
    broken.input_count = 101  # one record unaccounted for
    _, critical, _ = evaluate([broken], settings.quality, "b", "r", datetime(2026, 1, 1))
    assert any("reconcile" in c for c in critical)


def test_rule_dimensions() -> None:
    assert rule_dimension("missing:account_id") == "completeness"
    assert rule_dimension("duplicate") == "uniqueness"
    assert rule_dimension("unknown_ref:account_id") == "referential_integrity"
    assert rule_dimension("owner_mismatch") == "consistency"
    assert rule_dimension("currency_code:isin") == "validity"
    assert rule_dimension("freshness_lag_hours") == "freshness"
    assert rule_dimension("reconciliation") == "reconciliation"
