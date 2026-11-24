"""Bronze layer: raw, immutable, replayable.

Layout (relative to the lake root)::

    bronze/source=<system>/entity=<entity>/batch_date=<YYYY-MM-DD>/batch_id=<id>/data.<fmt>
    bronze/source=<system>/entity=<entity>/batch_date=<YYYY-MM-DD>/batch_id=<id>/_manifest.json
    bronze/_batches/batch_id=<id>.json        <- written last: marks the batch complete

Rules:

* The payload is stored byte-for-byte as received.
* An object is never overwritten. Re-ingesting identical bytes is a no-op; different
  bytes for an existing batch raise ``BronzeConflictError``.
* Once the batch marker exists, downstream steps read Bronze only, so a batch can
  be replayed long after the source has changed (or disappeared).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from finflow.common.errors import BronzeConflictError
from finflow.common.logging import get_logger
from finflow.common.storage import LakeStorage
from finflow.sources.models import BatchInfo, RawExtract, Record, parse_payload

log = get_logger("ingestion.bronze")


def sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def batch_marker_path(batch_id: str) -> str:
    return f"bronze/_batches/batch_id={batch_id}.json"


def entity_prefix(extract: RawExtract, batch: BatchInfo) -> str:
    return (
        f"bronze/source={extract.source_system}/entity={extract.entity}/"
        f"batch_date={batch.business_date.isoformat()}/batch_id={batch.batch_id}"
    )


@dataclass(frozen=True)
class BronzeEntity:
    entity: str
    source_system: str
    fmt: str
    data_path: str
    sha256: str
    record_count: int


def write_entity(
    storage: LakeStorage, batch: BatchInfo, extract: RawExtract, watermark_before: datetime | None
) -> BronzeEntity:
    prefix = entity_prefix(extract, batch)
    data_path = f"{prefix}/data.{extract.fmt}"
    manifest_path = f"{prefix}/_manifest.json"
    checksum = sha256(extract.payload)

    if storage.exists(manifest_path):
        existing = json.loads(storage.read_bytes(manifest_path))
        if existing["sha256"] != checksum:
            raise BronzeConflictError(
                f"{batch.batch_id}/{extract.entity} already in Bronze with checksum "
                f"{existing['sha256'][:12]}, new payload is {checksum[:12]}. Refusing to overwrite."
            )
        log.info("bronze object already present, skipping", extra={"entity": extract.entity})
    else:
        storage.write_bytes(data_path, extract.payload)
        manifest: dict[str, Any] = {
            "batch_id": batch.batch_id,
            "entity": extract.entity,
            "source_system": extract.source_system,
            "source_type": extract.source_type,
            "format": extract.fmt,
            "data_path": data_path,
            "sha256": checksum,
            "bytes": len(extract.payload),
            "record_count": extract.record_count,
            "extracted_at": extract.extracted_at.isoformat(),
            "ingested_at": datetime.now(UTC).replace(tzinfo=None).isoformat(),
            "batch_window": [batch.window_start.isoformat(), batch.window_end.isoformat()],
            "watermark_before": watermark_before.isoformat() if watermark_before else None,
        }
        # The manifest is written after the data: its presence means the data is complete.
        storage.write_bytes(manifest_path, json.dumps(manifest, indent=2).encode())
    return BronzeEntity(
        extract.entity, extract.source_system, extract.fmt, data_path, checksum, extract.record_count
    )


def write_batch_marker(storage: LakeStorage, batch: BatchInfo, entities: list[BronzeEntity]) -> None:
    marker = {
        **batch.to_dict(),
        "completed_at": datetime.now(UTC).replace(tzinfo=None).isoformat(),
        "objects": [e.__dict__ for e in entities],
    }
    storage.write_bytes(batch_marker_path(batch.batch_id), json.dumps(marker, indent=2).encode())


def read_batch_marker(storage: LakeStorage, batch_id: str) -> dict[str, Any] | None:
    path = batch_marker_path(batch_id)
    if not storage.exists(path):
        return None
    marker: dict[str, Any] = json.loads(storage.read_bytes(path))
    return marker


def read_entity_records(storage: LakeStorage, obj: dict[str, Any]) -> list[Record]:
    """Replay one Bronze object, verifying it has not been tampered with."""
    payload = storage.read_bytes(obj["data_path"])
    if sha256(payload) != obj["sha256"]:
        raise BronzeConflictError(f"Checksum mismatch for {obj['data_path']}: Bronze object was modified.")
    return parse_payload(obj["fmt"], payload)
