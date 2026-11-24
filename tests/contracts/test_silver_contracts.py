"""Silver datasets are a contract with the warehouse: column names and dtypes are fixed."""

from datetime import datetime
from pathlib import Path

import pytest

from finflow.common.config import Settings, load_settings
from finflow.generators.synthetic import SyntheticGenerator
from finflow.transformations.silver import TransformContext, transform_entity
from finflow.validation.contracts import CONTRACTS, PROCESSING_ORDER

LINEAGE = {"batch_id": "string", "source_system": "string", "ingested_at": "datetime64[us]"}

EXPECTED = {
    "transactions": {
        "transaction_id": "string",
        "account_id": "string",
        "customer_id": "string",
        "transaction_type": "string",
        "amount_minor": "Int64",
        "currency_code": "string",
        "status": "string",
        "channel": "string",
        "event_ts": "datetime64[us]",
        "card_id": "string",
        "merchant_id": "string",
        "counterparty_account_id": "string",
        "txn_date": "datetime64[us]",
        "rate_micros": "Int64",
        "amount_mxn_minor": "Int64",
        "is_late_arriving": "boolean",
        "is_risk_flagged": "boolean",
        "risk_reasons": "string",
    },
    "customers": {
        "customer_id": "string",
        "first_name": "string",
        "last_name": "string",
        "segment": "string",
        "created_at": "datetime64[us]",
        "updated_at": "datetime64[us]",
        "email": "string",
        "city": "string",
        "state": "string",
        "attributes_hash": "string",
    },
    "exchange_rates": {
        "rate_date": "datetime64[us]",
        "currency_code": "string",
        "rate_to_mxn_micros": "Int64",
        "rate_key": "string",
    },
    "loan_payments": {
        "payment_id": "string",
        "loan_id": "string",
        "installment_number": "Int64",
        "due_date": "datetime64[us]",
        "amount_minor": "Int64",
        "principal_component_minor": "Int64",
        "interest_component_minor": "Int64",
        "status": "string",
        "updated_at": "datetime64[us]",
        "paid_at": "datetime64[us]",
    },
}


@pytest.fixture(scope="module")
def silver(tmp_path_factory: pytest.TempPathFactory) -> dict:
    settings: Settings = load_settings("lightweight", home=Path(__file__).resolve().parents[2])
    batch = SyntheticGenerator(settings.generation).historical_batch()
    ctx = TransformContext(
        "b000", "test", datetime(2026, 2, 1), datetime(2026, 1, 1), datetime(2026, 1, 31), settings.risk
    )
    out = {}
    for entity in PROCESSING_ORDER:
        result = transform_entity(CONTRACTS[entity], batch.entities[entity], ctx)
        ctx.known_keys[entity] = set(result.accepted[CONTRACTS[entity].natural_key])
        if entity == "accounts":
            ctx.account_owner = dict(
                zip(result.accepted["account_id"], result.accepted["customer_id"], strict=True)
            )
        if entity == "exchange_rates":
            ctx.rates = result.accepted
        out[entity] = result.accepted
    return out


@pytest.mark.parametrize("entity", sorted(EXPECTED))
def test_silver_schema(silver: dict, entity: str) -> None:
    actual = {c: str(t) for c, t in silver[entity].dtypes.items()}
    assert actual == {**EXPECTED[entity], **LINEAGE}


@pytest.mark.parametrize("entity", PROCESSING_ORDER)
def test_silver_natural_keys_are_unique_and_lineage_present(silver: dict, entity: str) -> None:
    frame = silver[entity]
    assert frame[CONTRACTS[entity].natural_key].is_unique
    assert frame[["batch_id", "source_system", "ingested_at"]].notna().all().all()


def test_money_columns_are_integers_never_floats(silver: dict) -> None:
    for frame in silver.values():
        for column in frame.columns:
            if column.endswith(("_minor", "_micros")):
                assert str(frame[column].dtype) == "Int64", column
