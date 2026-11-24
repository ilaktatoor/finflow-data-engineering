"""Operational PostgreSQL source (core banking + lending).

``seed_batch`` plays the part of the operational applications writing their
own database; ``OperationalSource`` is the pipeline reading from it
incrementally with an ``updated_at`` watermark.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import sqlalchemy as sa

from finflow.generators.synthetic import FILE_FORMATS
from finflow.sources.models import BatchInfo, RawExtract, parse_payload, to_jsonl
from finflow.validation.contracts import CONTRACTS

TABLES = {
    "customers": "customers",
    "accounts": "accounts",
    "loans": "loans",
    "loan_payments": "loan_payments",
}


class OperationalSource:
    source_type = "database"
    entities = tuple(TABLES)

    def __init__(self, url: str) -> None:
        self.engine = sa.create_engine(url, pool_pre_ping=True)

    def extract(self, entity: str, batch: BatchInfo, watermark: datetime | None) -> RawExtract | None:
        table = TABLES[entity]
        columns = ", ".join(CONTRACTS[entity].columns)
        # Half-open window (watermark, window_end]: each change is read exactly once.
        query = sa.text(
            f"SELECT {columns} FROM {table} "
            "WHERE updated_at > :lower AND updated_at <= :upper ORDER BY updated_at"
        )
        with self.engine.connect() as conn:
            rows = (
                conn.execute(query, {"lower": watermark or datetime(1900, 1, 1), "upper": batch.window_end})
                .mappings()
                .all()
            )
        if not rows:
            return None
        return RawExtract(
            entity=entity,
            source_system=CONTRACTS[entity].data_system,
            source_type=self.source_type,
            fmt="jsonl",
            payload=to_jsonl([dict(r) for r in rows]),
            record_count=len(rows),
            extracted_at=datetime.now(UTC).replace(tzinfo=None),
        )


def seed_batch(url: str, landing_dir: Path, batch: BatchInfo, schema_sql: Path) -> dict[str, int]:
    """Upsert one landing batch into the operational database (simulated app writes)."""
    engine = sa.create_engine(url)
    counts: dict[str, int] = {}
    with engine.begin() as conn:
        conn.exec_driver_sql(schema_sql.read_text())
        for entity, table in TABLES.items():
            path = landing_dir / batch.batch_id / f"{entity}.{FILE_FORMATS[entity]}"
            if not path.is_file():
                continue
            records = parse_payload(FILE_FORMATS[entity], path.read_bytes())
            columns = list(CONTRACTS[entity].columns)
            key = CONTRACTS[entity].natural_key
            updates = ", ".join(f"{c} = EXCLUDED.{c}" for c in columns if c != key)
            statement = sa.text(
                f"INSERT INTO {table} ({', '.join(columns)}) "
                f"VALUES ({', '.join(':' + c for c in columns)}) "
                f"ON CONFLICT ({key}) DO UPDATE SET {updates}"
            )
            rows = [{c: (r.get(c) or None) for c in columns} for r in records]
            conn.execute(statement, rows)
            counts[entity] = len(rows)
        conn.execute(
            sa.text(
                "INSERT INTO seeded_batches (batch_id, seeded_at) VALUES (:b, :t) "
                "ON CONFLICT (batch_id) DO NOTHING"
            ),
            {"b": batch.batch_id, "t": datetime.now(UTC).replace(tzinfo=None)},
        )
    return counts
