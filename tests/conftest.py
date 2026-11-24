"""Shared fixtures. Everything runs against temporary directories; nothing touches ./data."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from finflow.common.config import Settings, load_settings

if TYPE_CHECKING:  # imported lazily so early modules can be tested on their own
    from finflow.transformations.silver import TransformContext

REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Settings:
    monkeypatch.setenv("FINFLOW_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.delenv("FINFLOW_MODE", raising=False)
    monkeypatch.delenv("FINFLOW_FAIL_AT", raising=False)
    return load_settings("lightweight", home=REPO_ROOT)


@pytest.fixture
def ctx(settings: Settings) -> TransformContext:
    """A transform context with a tiny reference universe."""
    import pandas as pd

    from finflow.transformations.silver import TransformContext

    context = TransformContext(
        batch_id="b-test",
        source_system="unit_test",
        ingested_at=datetime(2026, 2, 1),
        window_start=datetime(2026, 1, 1),
        window_end=datetime(2026, 1, 31),
        risk=settings.risk,
    )
    context.known_keys = {
        "customers": {"C00001", "C00002"},
        "accounts": {"A000001", "A000002"},
        "merchants": {"M0001"},
        "cards": {"K000001"},
        "loans": {"L00001"},
    }
    context.account_owner = {"A000001": "C00001", "A000002": "C00002"}
    context.rates = pd.DataFrame(
        {
            "currency_code": ["USD"],
            "rate_date": [pd.Timestamp("2026-01-10")],
            "rate_to_mxn_micros": pd.array([17_500_000], dtype="Int64"),
        }
    )
    return context


@pytest.fixture
def valid_transaction() -> dict[str, str | None]:
    return {
        "transaction_id": "T000000001",
        "account_id": "A000001",
        "customer_id": "C00001",
        "card_id": "K000001",
        "merchant_id": "M0001",
        "counterparty_account_id": None,
        "transaction_type": "PURCHASE",
        "amount": "100.50",
        "currency_code": "MXN",
        "status": "COMPLETED",
        "channel": "CARD_POS",
        "event_ts": "2026-01-10T12:00:00Z",
    }
