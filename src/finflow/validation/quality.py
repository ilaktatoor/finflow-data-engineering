"""Turn per-entity transformation results into quality measurements and a gate decision."""

from __future__ import annotations

from datetime import datetime
from typing import Any

import pandas as pd

from finflow.common.config import QualityConfig
from finflow.transformations.silver import EntityResult


def rule_dimension(rule: str) -> str:
    if rule.startswith("missing:"):
        return "completeness"
    if rule == "duplicate":
        return "uniqueness"
    if rule.startswith("unknown_ref:"):
        return "referential_integrity"
    if rule.startswith("business:") or rule in ("owner_mismatch", "missing_exchange_rate"):
        return "consistency"
    if rule in ("freshness_lag_hours", "reconciliation"):
        return "freshness" if rule.startswith("freshness") else "reconciliation"
    if rule == "reject_rate":
        return "gate"
    return "validity"  # schema_mismatch, invalid_format:*, <col>:<check>


def evaluate(
    results: list[EntityResult], quality: QualityConfig, batch_id: str, run_id: str, measured_at: datetime
) -> tuple[pd.DataFrame, list[str], dict[str, Any]]:
    """Return (fact_data_quality rows, critical failures, JSON report)."""
    rows: list[dict[str, Any]] = []
    critical: list[str] = []
    report: dict[str, Any] = {"batch_id": batch_id, "run_id": run_id, "entities": {}}

    def add(
        entity: str, rule: str, failed: int, checked: int, severity: str, value: float | None = None
    ) -> None:
        rows.append(
            {
                "batch_id": batch_id,
                "entity": entity,
                "rule_name": rule,
                "dimension": rule_dimension(rule),
                "severity": severity,
                "failed_records": failed,
                "checked_records": checked,
                "measured_value": value,
                "run_id": run_id,
                "measured_at": measured_at,
            }
        )

    for result in results:
        n = result.input_count
        for rule, failed in sorted(result.rule_failures.items()):
            add(result.entity, rule, failed, n, "warning" if failed else "info")

        reconciles = result.reconciles()
        add(result.entity, "reconciliation", 0 if reconciles else 1, 1, "info" if reconciles else "critical")
        if not reconciles:
            critical.append(f"{result.entity}: input does not reconcile with accepted+rejected+duplicates")

        rate = result.reject_rate
        if rate > quality.max_reject_rate:
            severity = "critical"
            critical.append(
                f"{result.entity}: reject rate {rate:.2%} exceeds the critical threshold "
                f"{quality.max_reject_rate:.2%}"
            )
        elif rate > quality.warn_reject_rate:
            severity = "warning"
        else:
            severity = "info"
        add(result.entity, "reject_rate", result.rejected_count, n, severity, round(rate, 6))

        if result.freshness_lag_hours is not None:
            stale = result.freshness_lag_hours > quality.max_freshness_lag_hours
            add(
                result.entity,
                "freshness_lag_hours",
                int(stale),
                1,
                "warning" if stale else "info",
                result.freshness_lag_hours,
            )

        report["entities"][result.entity] = {
            "input": n,
            "accepted": result.accepted_count,
            "rejected": result.rejected_count,
            "duplicates": result.duplicate_count,
            "reject_rate": round(rate, 6),
            "reject_rate_severity": severity,
            "freshness_lag_hours": result.freshness_lag_hours,
            "reconciles": reconciles,
            "rule_failures": {k: v for k, v in sorted(result.rule_failures.items()) if v},
        }

    report["status"] = "failed" if critical else "passed"
    report["critical_failures"] = critical
    return pd.DataFrame(rows), critical, report
