"""HTTP extraction from the source simulator, with retries and pagination."""

from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from finflow.common.errors import SourceError
from finflow.common.logging import get_logger
from finflow.sources.models import BatchInfo, RawExtract, to_jsonl
from finflow.validation.contracts import CONTRACTS

log = get_logger("sources.api")


class ApiSource:
    source_type = "api"
    entities = ("merchants", "exchange_rates")

    def __init__(
        self,
        base_url: str,
        *,
        attempts: int = 3,
        backoff_seconds: float = 1.0,
        client: httpx.Client | None = None,
    ) -> None:
        self.client = client or httpx.Client(base_url=base_url, timeout=10.0)
        self.attempts = attempts
        self.backoff_seconds = backoff_seconds

    def _get(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        for attempt in range(1, self.attempts + 1):
            try:
                response = self.client.get(path, params=params)
                response.raise_for_status()
                body: dict[str, Any] = response.json()
                return body
            except (httpx.TransportError, httpx.HTTPStatusError) as exc:
                # Client errors (4xx) will not fix themselves; only retry 5xx and transport errors.
                if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code < 500:
                    raise SourceError(f"GET {path} failed: {exc}") from exc
                if attempt == self.attempts:
                    raise SourceError(f"GET {path} failed after {attempt} attempts: {exc}") from exc
                log.warning("api request failed, retrying", extra={"path": path, "attempt": attempt})
                time.sleep(self.backoff_seconds * 2 ** (attempt - 1))
        raise AssertionError("unreachable")

    def _paginate(self, path: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        offset = 0
        while True:
            page = self._get(path, {**params, "offset": offset})
            items.extend(page["items"])
            offset += len(page["items"])
            if not page["items"] or offset >= page["total"]:
                return items

    def extract(self, entity: str, batch: BatchInfo, watermark: datetime | None) -> RawExtract | None:
        """Pull records changed after ``watermark`` and up to the batch window end."""
        if entity == "merchants":
            params: dict[str, Any] = {"updated_until": batch.window_end.isoformat()}
            if watermark is not None:
                params["updated_after"] = watermark.isoformat()
            records = self._paginate("/merchants", params)
        elif entity == "exchange_rates":
            # The watermark is the previous window's (exclusive) end, i.e. the first
            # day that has not been extracted yet.
            start = watermark.date() if watermark else None
            params = {"end_date": (batch.window_end - timedelta(seconds=1)).date().isoformat()}
            if start is not None:
                params["start_date"] = start.isoformat()
            records = self._paginate("/exchange-rates", params)
        else:
            raise ValueError(f"The API does not serve '{entity}'")
        if not records:
            return None
        return RawExtract(
            entity=entity,
            source_system=CONTRACTS[entity].data_system,
            source_type=self.source_type,
            fmt="jsonl",
            payload=to_jsonl(records),
            record_count=len(records),
            extracted_at=datetime.now(UTC).replace(tzinfo=None),
        )
