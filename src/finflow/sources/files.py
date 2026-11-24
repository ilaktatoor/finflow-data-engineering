"""File source: exports dropped by operational systems into the landing zone."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from finflow.generators.synthetic import FILE_FORMATS
from finflow.sources.models import BatchInfo, RawExtract, parse_payload
from finflow.validation.contracts import CONTRACTS


class FileSource:
    source_type = "file"

    def __init__(self, landing_dir: Path) -> None:
        self.landing_dir = landing_dir

    def extract(self, entity: str, batch: BatchInfo) -> RawExtract | None:
        fmt = FILE_FORMATS[entity]
        path = self.landing_dir / batch.batch_id / f"{entity}.{fmt}"
        if not path.is_file():
            return None  # this batch carries no export for the entity
        payload = path.read_bytes()  # original bytes, preserved as-is in Bronze
        return RawExtract(
            entity=entity,
            source_system=CONTRACTS[entity].file_system,
            source_type=self.source_type,
            fmt=fmt,
            payload=payload,
            record_count=len(parse_payload(fmt, payload)),
            extracted_at=datetime.now(UTC).replace(tzinfo=None),
        )
