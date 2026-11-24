"""Shapes shared by every source adapter."""

from __future__ import annotations

import csv
import io
import json
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

Record = dict[str, Any]


@dataclass(frozen=True)
class BatchInfo:
    """Control-plane description of a batch, read from ``landing/<batch_id>/_batch.json``."""

    batch_id: str
    sequence: int
    batch_type: str
    business_date: date
    window_start: datetime  # naive UTC
    window_end: datetime  # naive UTC
    entities: tuple[str, ...]

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> BatchInfo:
        def ts(value: str) -> datetime:
            return datetime.fromisoformat(value).astimezone(UTC).replace(tzinfo=None)

        return cls(
            batch_id=raw["batch_id"],
            sequence=int(raw["sequence"]),
            batch_type=raw["batch_type"],
            business_date=date.fromisoformat(raw["business_date"]),
            window_start=ts(raw["window_start"]),
            window_end=ts(raw["window_end"]),
            entities=tuple(raw["entities"]),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "batch_id": self.batch_id,
            "sequence": self.sequence,
            "batch_type": self.batch_type,
            "business_date": self.business_date.isoformat(),
            "window_start": self.window_start.isoformat(),
            "window_end": self.window_end.isoformat(),
            "entities": list(self.entities),
        }


@dataclass(frozen=True)
class RawExtract:
    """Exactly what a source returned, before any interpretation."""

    entity: str
    source_system: str
    source_type: str  # file | api | database
    fmt: str  # csv | json | jsonl
    payload: bytes
    record_count: int
    extracted_at: datetime


def parse_payload(fmt: str, payload: bytes) -> list[Record]:
    """Turn raw bytes back into records. Values stay as the source sent them."""
    text = payload.decode("utf-8")
    if fmt == "csv":
        return list(csv.DictReader(io.StringIO(text)))
    if fmt == "json":
        data = json.loads(text)
        if not isinstance(data, list):
            raise ValueError("JSON payloads must contain a list of records")
        return data
    if fmt == "jsonl":
        return [json.loads(line) for line in text.splitlines() if line.strip()]
    raise ValueError(f"Unsupported format: {fmt}")


def to_jsonl(records: list[Record]) -> bytes:
    """Serialize API/database rows; values are stringified like a file export."""

    def text(value: Any) -> Any:
        if value is None or isinstance(value, str):
            return value
        if isinstance(value, datetime):
            return value.strftime("%Y-%m-%dT%H:%M:%SZ")
        if isinstance(value, date):
            return value.isoformat()
        return str(value)

    return "".join(
        json.dumps({k: text(v) for k, v in r.items()}, ensure_ascii=False) + "\n" for r in records
    ).encode("utf-8")


def list_landing_batches(landing_dir: Path) -> list[BatchInfo]:
    manifests = [json.loads(p.read_text()) for p in landing_dir.glob("*/_batch.json")]
    return sorted((BatchInfo.from_dict(m) for m in manifests), key=lambda b: b.sequence)


def load_landing_batch(landing_dir: Path, batch_id: str) -> BatchInfo:
    path = landing_dir / batch_id / "_batch.json"
    if not path.is_file():
        raise FileNotFoundError(f"Batch '{batch_id}' not found in {landing_dir}")
    return BatchInfo.from_dict(json.loads(path.read_text()))
