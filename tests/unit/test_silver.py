from typing import Any

import pytest

from finflow.transformations.silver import TransformContext, transform_entity
from finflow.validation.contracts import CONTRACTS

TXN = CONTRACTS["transactions"]


def run(records: list[dict[str, Any]], ctx: TransformContext):  # type: ignore[no-untyped-def]
    return transform_entity(TXN, records, ctx)


def reasons_of(result) -> dict[str, str]:  # type: ignore[no-untyped-def]
    return dict(zip(result.quarantine["natural_key"], result.quarantine["reasons"], strict=True))


def test_valid_record_is_accepted_and_typed(ctx: TransformContext, valid_transaction: dict) -> None:
    result = run([valid_transaction], ctx)
    assert result.accepted_count == 1 and result.rejected_count == 0
    row = result.accepted.iloc[0]
    assert row["amount_minor"] == 10_050
    assert row["amount_mxn_minor"] == 10_050
    assert row["batch_id"] == "b-test" and row["source_system"] == "unit_test"
    assert not row["is_late_arriving"]


@pytest.mark.parametrize(
    ("change", "expected_reason"),
    [
        ({"currency_code": "XYZ"}, "currency_code:isin"),
        ({"status": "DONE"}, "status:isin"),
        ({"event_ts": "2026-13-45T25:61:00Z"}, "invalid_format:event_ts"),
        ({"amount": "12,34.5x"}, "invalid_format:amount"),
        ({"amount": "0.00"}, "amount:greater_than"),
        ({"account_id": None}, "missing:account_id"),
        ({"account_id": "A999999"}, "unknown_ref:account_id"),
        ({"merchant_id": "M9999"}, "unknown_ref:merchant_id"),
        ({"customer_id": "C00002"}, "owner_mismatch"),
        ({"merchant_id": None}, "business:purchase_requires_merchant"),
        (
            {"transaction_type": "TRANSFER", "card_id": None, "merchant_id": None},
            "business:transfer_requires_counterparty",
        ),
    ],
)
def test_invalid_records_are_quarantined_with_reason(
    ctx: TransformContext, valid_transaction: dict, change: dict, expected_reason: str
) -> None:
    result = run([{**valid_transaction, **change}], ctx)
    assert result.accepted_count == 0 and result.rejected_count == 1
    assert expected_reason in reasons_of(result)["T000000001"].split("|")
    assert result.reconciles()


def test_schema_mismatch_is_reported_once(ctx: TransformContext, valid_transaction: dict) -> None:
    record = dict(valid_transaction)
    record["txn_amount"] = record.pop("amount")
    result = run([record], ctx)
    assert reasons_of(result)["T000000001"] == "schema_mismatch"


def test_duplicates_are_separated_not_rejected(ctx: TransformContext, valid_transaction: dict) -> None:
    result = run([valid_transaction, dict(valid_transaction)], ctx)
    assert (result.accepted_count, result.rejected_count, result.duplicate_count) == (1, 0, 1)
    assert result.rule_failures["duplicate"] == 1
    assert result.reconciles()


def test_valid_record_wins_over_invalid_duplicate_key(ctx: TransformContext, valid_transaction: dict) -> None:
    broken = {**valid_transaction, "status": "DONE"}
    result = run([broken, valid_transaction], ctx)
    assert (result.accepted_count, result.rejected_count, result.duplicate_count) == (1, 1, 0)


def test_foreign_currency_is_converted_with_exact_rate(
    ctx: TransformContext, valid_transaction: dict
) -> None:
    result = run([{**valid_transaction, "currency_code": "usd", "amount": "10.00"}], ctx)
    row = result.accepted.iloc[0]
    assert row["currency_code"] == "USD"
    assert row["amount_mxn_minor"] == 17_500  # 10.00 * 17.5


def test_missing_exchange_rate_is_rejected(ctx: TransformContext, valid_transaction: dict) -> None:
    result = run([{**valid_transaction, "currency_code": "EUR"}], ctx)
    assert "missing_exchange_rate" in reasons_of(result)["T000000001"]


def test_late_arriving_flag(ctx: TransformContext, valid_transaction: dict) -> None:
    result = run([{**valid_transaction, "event_ts": "2025-12-30T10:00:00Z"}], ctx)
    assert bool(result.accepted.iloc[0]["is_late_arriving"])


def test_raw_payload_is_preserved_in_quarantine(ctx: TransformContext, valid_transaction: dict) -> None:
    result = run([{**valid_transaction, "amount": "$100"}], ctx)
    assert '"amount": "$100"' in result.quarantine.iloc[0]["raw_record"]


def test_loan_payment_components_must_reconcile(ctx: TransformContext) -> None:
    payment = {
        "payment_id": "P00001001",
        "loan_id": "L00001",
        "installment_number": "1",
        "due_date": "2026-01-05",
        "paid_at": "2026-01-05T10:00:00Z",
        "amount": "100.00",
        "principal_component": "60.00",
        "interest_component": "30.00",
        "status": "ON_TIME",
        "updated_at": "2026-01-05T10:00:00Z",
    }
    result = transform_entity(CONTRACTS["loan_payments"], [payment], ctx)
    assert "business:payment_components_reconcile" in result.quarantine.iloc[0]["reasons"]


def test_empty_input(ctx: TransformContext) -> None:
    result = run([], ctx)
    assert result.input_count == 0 and result.reconciles()
