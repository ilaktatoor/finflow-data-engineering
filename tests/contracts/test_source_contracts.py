"""The generator (our stand-in for upstream producers) must honour the published contracts."""

import pytest

from finflow.common.config import Settings
from finflow.generators.synthetic import FILE_FORMATS, SyntheticGenerator
from finflow.validation.contracts import CONTRACTS, PROCESSING_ORDER


def test_every_entity_has_a_contract_and_a_file_format() -> None:
    assert set(CONTRACTS) == set(FILE_FORMATS) == set(PROCESSING_ORDER)


@pytest.mark.parametrize("entity", sorted(CONTRACTS))
def test_clean_records_match_contract_fields(settings: Settings, entity: str) -> None:
    universe = SyntheticGenerator(settings.generation).build_universe()
    batch = SyntheticGenerator(settings.generation).historical_batch()
    records = getattr(universe, entity, None) or batch.entities[entity]
    contract = CONTRACTS[entity]
    for record in records:
        assert set(record) == set(contract.columns), f"{entity} fields drifted from the contract"
        missing = [f for f in contract.required if record[f] in (None, "")]
        assert not missing, f"{entity} {record.get(contract.natural_key, '')} misses {missing}"


def test_references_point_to_known_entities() -> None:
    for contract in CONTRACTS.values():
        for referenced in contract.references.values():
            assert referenced in CONTRACTS
