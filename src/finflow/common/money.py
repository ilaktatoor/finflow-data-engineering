"""Exact money handling.

Amounts are stored as integer *minor units* (cents) in ``Int64`` columns and
exchange rates as integer *micros* (rate x 1,000,000). All arithmetic is integer
arithmetic, so no binary floating-point rounding ever touches a financial amount.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

import pandas as pd

# Up to 12 integer digits and at most 2 decimals, optional leading minus.
AMOUNT_PATTERN = r"-?\d{1,12}(?:\.\d{1,2})?"
RATE_PATTERN = r"\d{1,6}(?:\.\d{1,6})?"


def _parse_fixed_point(values: pd.Series, pattern: str, scale_digits: int) -> pd.Series:
    """Parse decimal strings into scaled integers. Invalid input becomes <NA>.

    Vectorised: split on the decimal point and combine the integer and the
    right-padded fractional part, instead of converting through ``float``.
    """
    if values.empty:  # str.split(expand=True) on an empty Series yields no columns
        return pd.Series(index=values.index, dtype="Int64")
    text = values.astype("string").str.strip()
    valid = text.str.fullmatch(pattern).fillna(False).astype(bool)
    clean = text.where(valid)
    negative = clean.str.startswith("-").fillna(False).astype(bool)
    unsigned = clean.str.lstrip("-")
    parts = unsigned.str.split(".", n=1, expand=True)
    if parts.shape[1] == 1:
        parts[1] = pd.NA
    integer = pd.to_numeric(parts[0], errors="coerce").astype("Int64")
    fraction_text = parts[1].fillna("").str.ljust(scale_digits, "0")
    fraction = pd.to_numeric(fraction_text, errors="coerce").astype("Int64")
    scaled = integer * (10**scale_digits) + fraction
    scaled = scaled.where(~negative, -scaled)
    return scaled.where(valid).astype("Int64")


def parse_amount_minor(values: pd.Series) -> pd.Series:
    """``"1234.5"`` -> ``123450``. Malformed amounts become ``<NA>``."""
    return _parse_fixed_point(values, AMOUNT_PATTERN, 2)


def parse_rate_micros(values: pd.Series) -> pd.Series:
    """``"17.25"`` -> ``17250000``. Malformed rates become ``<NA>``."""
    return _parse_fixed_point(values, RATE_PATTERN, 6)


def convert_minor(amount_minor: pd.Series, rate_micros: pd.Series) -> pd.Series:
    """Convert minor units with a rate in micros, rounding half away from zero.

    ``amount * rate`` stays far below 2**63 for amounts up to 10^12 minor units
    and rates below 10^7 micros, so ``Int64`` cannot overflow here.
    """
    product = amount_minor.astype("Int64") * rate_micros.astype("Int64")
    sign = product.where(product >= 0, -1).where(product < 0, 1)
    return (sign * ((product.abs() + 500_000) // 1_000_000)).astype("Int64")


def to_minor(amount: Decimal) -> int:
    return int((amount * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def format_minor(minor: int) -> str:
    """``123450`` -> ``"1234.50"`` (used for human-readable reports)."""
    return str((Decimal(minor) / 100).quantize(Decimal("0.01")))
