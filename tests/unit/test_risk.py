import pandas as pd

from finflow.common.config import Settings
from finflow.transformations.risk import flag_transactions


def frame(rows: list[tuple[str, str, int, str]]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "account_id": [r[0] for r in rows],
            "event_ts": pd.to_datetime([r[1] for r in rows]).astype("datetime64[us]"),
            "amount_mxn_minor": pd.array([r[2] for r in rows], dtype="Int64"),
            "currency_code": [r[3] for r in rows],
        },
        index=[10 + i for i in range(len(rows))],  # non-default labels must survive
    )


def test_velocity_flags_fourth_transaction_in_window(settings: Settings) -> None:
    rows = [("A1", f"2026-01-01 10:0{i}:00", 1_000, "MXN") for i in range(4)]
    rows.append(("A2", "2026-01-01 10:00:00", 1_000, "MXN"))
    out = flag_transactions(frame(rows), settings.risk)
    assert out["risk_reasons"].fillna("").tolist() == ["", "", "", "VELOCITY", ""]
    assert out.index.tolist() == [10, 11, 12, 13, 14]


def test_high_amount_and_foreign_night(settings: Settings) -> None:
    out = flag_transactions(
        frame([("A1", "2026-01-01 03:00:00", 6_000_000, "USD"), ("A2", "2026-01-01 12:00:00", 100, "USD")]),
        settings.risk,
    )
    assert out["risk_reasons"].iloc[0] == "HIGH_AMOUNT|FOREIGN_NIGHT"
    assert not out["is_risk_flagged"].iloc[1]


def test_empty_frame(settings: Settings) -> None:
    out = flag_transactions(frame([]), settings.risk)
    assert out.empty and "is_risk_flagged" in out
