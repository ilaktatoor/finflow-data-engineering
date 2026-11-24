"""Simulated risk rules.

These rules exist to demonstrate window functions and vectorised flags. They are
not a fraud detection model and have never been validated against real fraud.
"""

from __future__ import annotations

import pandas as pd

from finflow.common.config import RiskConfig
from finflow.common.money import to_minor


def flag_transactions(df: pd.DataFrame, risk: RiskConfig) -> pd.DataFrame:
    """Add ``is_risk_flagged`` and ``risk_reasons`` (pipe-separated rule codes)."""
    out = df.copy()
    if out.empty:
        out["is_risk_flagged"] = pd.Series(dtype="boolean")
        out["risk_reasons"] = pd.Series(dtype="string")
        return out

    high_amount = out["amount_mxn_minor"] >= to_minor(risk.high_amount_mxn)

    # Velocity: how many transactions the account made in the trailing window,
    # including this one. A time-based rolling window per account.
    ordered = out[["account_id", "event_ts"]].assign(_one=1).sort_values(["account_id", "event_ts"])
    rolled = (
        ordered.groupby("account_id")
        .rolling(f"{risk.velocity_window_minutes}min", on="event_ts")["_one"]
        .sum()
    )
    # pandas indexes the result by (account_id, event_ts); because `ordered` is
    # already sorted by both, positions line up and we map back to row labels.
    trailing = pd.Series(rolled.to_numpy(), index=ordered.index)
    velocity = trailing.reindex(out.index) > risk.velocity_max_transactions

    hour = out["event_ts"].dt.hour
    foreign_night = (out["currency_code"] != "MXN") & hour.between(
        risk.night_start_hour, risk.night_end_hour - 1
    )

    reasons = (
        high_amount.map({True: "HIGH_AMOUNT|", False: ""}).astype("string")
        + velocity.map({True: "VELOCITY|", False: ""}).astype("string")
        + foreign_night.map({True: "FOREIGN_NIGHT|", False: ""}).astype("string")
    ).str.rstrip("|")
    out["is_risk_flagged"] = (reasons != "").astype("boolean")
    out["risk_reasons"] = reasons.where(reasons != "")
    return out
