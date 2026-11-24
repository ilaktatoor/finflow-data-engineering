"""FastAPI source simulator: a merchant registry and a treasury rates service.

It serves records from the landing zone, filtered by time window, the way a real
upstream API would expose them. Run with ``finflow serve-api``.
"""

from __future__ import annotations

import os
from datetime import date, datetime
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query

from finflow.sources.models import list_landing_batches, parse_payload

PAGE_LIMIT = 100


def _landing_dir() -> Path:
    return Path(os.environ.get("FINFLOW_LANDING_DIR", "data/landing"))


def _all_records(entity: str, fmt: str, key: str) -> list[dict[str, Any]]:
    """Latest version of every record across batches (later batches win)."""
    landing = _landing_dir()
    latest: dict[str, dict[str, Any]] = {}
    for batch in list_landing_batches(landing):
        path = landing / batch.batch_id / f"{entity}.{fmt}"
        if path.is_file():
            for record in parse_payload(fmt, path.read_bytes()):
                latest[
                    str(record[key])
                    if key != "rate_key"
                    else f"{record['currency_code']}|{record['rate_date']}"
                ] = record
    return list(latest.values())


def _page(records: list[dict[str, Any]], offset: int, limit: int) -> dict[str, Any]:
    return {
        "total": len(records),
        "offset": offset,
        "limit": limit,
        "items": records[offset : offset + limit],
    }


app = FastAPI(title="FinFlow source simulator", version="0.1.0")


@app.get("/health")
def health() -> dict[str, str]:
    if not _landing_dir().is_dir():
        raise HTTPException(status_code=503, detail="landing directory not mounted")
    return {"status": "ok"}


@app.get("/merchants")
def merchants(
    updated_after: datetime | None = None,
    updated_until: datetime | None = None,
    offset: int = Query(0, ge=0),
    limit: int = Query(PAGE_LIMIT, ge=1, le=PAGE_LIMIT),
) -> dict[str, Any]:
    rows = sorted(_all_records("merchants", "json", "merchant_id"), key=lambda r: r["merchant_id"])

    def keep(r: dict[str, Any]) -> bool:
        ts = datetime.fromisoformat(r["updated_at"]).replace(tzinfo=None)
        lower = updated_after.replace(tzinfo=None) if updated_after else None
        upper = updated_until.replace(tzinfo=None) if updated_until else None
        return (lower is None or ts > lower) and (upper is None or ts <= upper)

    return _page([r for r in rows if keep(r)], offset, limit)


@app.get("/exchange-rates")
def exchange_rates(
    start_date: date | None = None,
    end_date: date | None = None,
    offset: int = Query(0, ge=0),
    limit: int = Query(PAGE_LIMIT, ge=1, le=PAGE_LIMIT),
) -> dict[str, Any]:
    rows = sorted(
        _all_records("exchange_rates", "csv", "rate_key"), key=lambda r: (r["rate_date"], r["currency_code"])
    )
    rows = [
        r
        for r in rows
        if (start_date is None or date.fromisoformat(r["rate_date"]) >= start_date)
        and (end_date is None or date.fromisoformat(r["rate_date"]) <= end_date)
    ]
    return _page(rows, offset, limit)
