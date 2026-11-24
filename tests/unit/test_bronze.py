from datetime import datetime
from pathlib import Path

import pytest

from finflow.common.errors import BronzeConflictError
from finflow.common.storage import LakeStorage
from finflow.ingestion import bronze
from finflow.sources.models import BatchInfo, RawExtract

BATCH = BatchInfo(
    "b001-2026-01-31",
    1,
    "incremental",
    datetime(2026, 1, 31).date(),
    datetime(2026, 1, 31),
    datetime(2026, 2, 1),
    ("transactions",),
)


def extract(payload: bytes) -> RawExtract:
    return RawExtract("transactions", "transaction_files", "file", "jsonl", payload, 1, datetime(2026, 2, 1))


def test_write_is_idempotent_for_identical_payload(tmp_path: Path) -> None:
    storage = LakeStorage.local(tmp_path)
    first = bronze.write_entity(storage, BATCH, extract(b'{"a": "1"}\n'), None)
    second = bronze.write_entity(storage, BATCH, extract(b'{"a": "1"}\n'), None)
    assert first == second
    assert first.data_path.startswith(
        "bronze/source=transaction_files/entity=transactions/batch_date=2026-01-31/batch_id=b001-2026-01-31/"
    )


def test_different_payload_for_same_batch_is_refused(tmp_path: Path) -> None:
    storage = LakeStorage.local(tmp_path)
    bronze.write_entity(storage, BATCH, extract(b'{"a": "1"}\n'), None)
    with pytest.raises(BronzeConflictError, match="Refusing to overwrite"):
        bronze.write_entity(storage, BATCH, extract(b'{"a": "2"}\n'), None)


def test_replay_detects_tampering(tmp_path: Path) -> None:
    storage = LakeStorage.local(tmp_path)
    written = bronze.write_entity(storage, BATCH, extract(b'{"a": "1"}\n'), None)
    bronze.write_batch_marker(storage, BATCH, [written])
    marker = bronze.read_batch_marker(storage, BATCH.batch_id)
    assert marker is not None
    assert bronze.read_entity_records(storage, marker["objects"][0]) == [{"a": "1"}]
    storage.write_bytes(written.data_path, b'{"a": "999"}\n')
    with pytest.raises(BronzeConflictError, match="Checksum mismatch"):
        bronze.read_entity_records(storage, marker["objects"][0])
