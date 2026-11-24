import pandas as pd
import pytest

from finflow.common.money import convert_minor, format_minor, parse_amount_minor, parse_rate_micros


def test_parse_amount_handles_valid_and_invalid_values() -> None:
    values = pd.Series(["100", "100.5", "100.05", "-3.10", "12,34.5x", "1.2.3", "$100", None, "1.234"])
    parsed = parse_amount_minor(values)
    assert parsed.tolist()[:4] == [10_000, 10_050, 10_005, -310]
    assert parsed.iloc[4:].isna().all()


def test_parse_amount_is_exact_where_float_is_not() -> None:
    # 0.1 + 0.2 != 0.3 in binary floating point; minor units keep it exact.
    parsed = parse_amount_minor(pd.Series(["0.10", "0.20", "0.30"]))
    assert parsed.iloc[0] + parsed.iloc[1] == parsed.iloc[2]
    big = parse_amount_minor(pd.Series(["999999999999.99"]))
    assert big.iloc[0] == 99_999_999_999_999


def test_parse_rate_micros() -> None:
    assert parse_rate_micros(pd.Series(["17.123456", "18", "bad"])).tolist()[:2] == [17_123_456, 18_000_000]


@pytest.mark.parametrize(
    ("amount", "rate", "expected"),
    [
        (10_000, 17_250_000, 172_500),  # 100.00 USD * 17.25 = 1725.00 MXN
        (1, 1_500_000, 2),  # 0.015 rounds half up to 0.02
        (1, 1_499_999, 1),
        (-1, 1_500_000, -2),  # half away from zero for negatives
    ],
)
def test_convert_minor_rounds_half_away_from_zero(amount: int, rate: int, expected: int) -> None:
    result = convert_minor(pd.Series([amount], dtype="Int64"), pd.Series([rate], dtype="Int64"))
    assert result.iloc[0] == expected


def test_format_minor() -> None:
    assert format_minor(123450) == "1234.50"
