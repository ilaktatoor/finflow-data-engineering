from dataclasses import replace

import pytest

from finflow.common.config import Settings
from finflow.generators.synthetic import ERROR_TYPES, SyntheticGenerator, serialize


def test_historical_batch_is_deterministic(settings: Settings) -> None:
    first = SyntheticGenerator(settings.generation).historical_batch()
    second = SyntheticGenerator(settings.generation).historical_batch()
    assert first.entities == second.entities
    assert serialize("transactions", first.entities["transactions"]) == serialize(
        "transactions", second.entities["transactions"]
    )


def test_seed_changes_output(settings: Settings) -> None:
    other = replace(settings.generation, seed=7)
    a = SyntheticGenerator(settings.generation).historical_batch().entities["transactions"]
    b = SyntheticGenerator(other).historical_batch().entities["transactions"]
    assert a != b


@pytest.mark.parametrize("profile", ["small", "medium", "large"])
def test_profile_sizes(settings: Settings, profile: str) -> None:
    size = settings.generation.profiles[profile]
    universe = SyntheticGenerator(settings.generation, profile).build_universe()
    assert len(universe.customers) == size.customers
    assert len(universe.transactions) == size.transactions <= 10_000
    assert len(universe.loan_payments) == size.loan_payments


def test_error_injection_is_counted_exactly(settings: Settings) -> None:
    batch = SyntheticGenerator(settings.generation).historical_batch()
    injected = batch.report["injected_errors"]
    assert set(injected) == set(ERROR_TYPES)
    expected_errors = round(
        settings.generation.profiles["small"].transactions * settings.generation.error_rate
    )
    assert sum(injected.values()) == expected_errors
    raw_count = len(batch.entities["transactions"])
    assert raw_count == settings.generation.profiles["small"].transactions + injected["duplicate"]


def test_incremental_batch_contains_late_records_and_corrections(settings: Settings) -> None:
    generator = SyntheticGenerator(settings.generation)
    batch = generator.incremental_batch(1)
    expected = batch.report["expected"]
    assert expected["late_arriving"] >= 3
    assert expected["status_corrections"] == 2
    assert len(batch.entities["customers"]) == 3  # SCD2 input
    ids = [t["transaction_id"] for t in batch.entities["transactions"]]
    assert any(i.startswith("T000") for i in ids)  # corrections re-send historical ids
    assert batch.batch_id == "b001-2026-01-31"


def test_incremental_sequence_must_be_positive(settings: Settings) -> None:
    with pytest.raises(ValueError, match="start at sequence 1"):
        SyntheticGenerator(settings.generation).incremental_batch(0)


def test_unknown_profile(settings: Settings) -> None:
    with pytest.raises(ValueError, match="Unknown profile"):
        SyntheticGenerator(settings.generation, "huge")
