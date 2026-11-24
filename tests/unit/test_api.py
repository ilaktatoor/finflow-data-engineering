import json
from datetime import datetime
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from finflow.common.config import Settings
from finflow.common.errors import SourceError
from finflow.generators.synthetic import SyntheticGenerator, write_batch
from finflow.sources.api import app
from finflow.sources.api_client import ApiSource
from finflow.sources.models import load_landing_batch, parse_payload


@pytest.fixture
def client(settings: Settings, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    write_batch(SyntheticGenerator(settings.generation).historical_batch(), settings.landing_dir, "small", 42)
    monkeypatch.setenv("FINFLOW_LANDING_DIR", str(settings.landing_dir))
    return TestClient(app)


def test_health(client: TestClient) -> None:
    assert client.get("/health").json() == {"status": "ok"}


def test_pagination_and_filters(client: TestClient) -> None:
    page = client.get("/exchange-rates", params={"limit": 40}).json()
    assert page["total"] == 90 and len(page["items"]) == 40
    one_day = client.get(
        "/exchange-rates", params={"start_date": "2026-01-05", "end_date": "2026-01-05"}
    ).json()
    assert {r["currency_code"] for r in one_day["items"]} == {"USD", "EUR", "CAD"}
    assert client.get("/exchange-rates", params={"limit": 1000}).status_code == 422


def test_api_source_paginates_and_respects_watermark(client: TestClient, settings: Settings) -> None:
    source = ApiSource("http://testserver", client=client)  # type: ignore[arg-type]
    batch = load_landing_batch(settings.landing_dir, "b000-historical")
    extract = source.extract("exchange_rates", batch, None)
    assert extract is not None and extract.record_count == 90  # needed two pages of 100 max
    assert len(parse_payload("jsonl", extract.payload)) == 90
    assert source.extract("exchange_rates", batch, datetime(2026, 1, 31)) is None
    merchants = source.extract("merchants", batch, None)
    assert merchants is not None and merchants.record_count == 30


def test_api_source_retries_server_errors_then_fails() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(503)

    source = ApiSource(
        "http://x",
        attempts=3,
        backoff_seconds=0,
        client=httpx.Client(base_url="http://x", transport=httpx.MockTransport(handler)),
    )
    with pytest.raises(SourceError, match="after 3 attempts"):
        source._get("/merchants", {})
    assert calls["n"] == 3


def test_api_source_does_not_retry_client_errors() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(404, json={"detail": "nope"})

    source = ApiSource(
        "http://x",
        backoff_seconds=0,
        client=httpx.Client(base_url="http://x", transport=httpx.MockTransport(handler)),
    )
    with pytest.raises(SourceError):
        source._get("/merchants", {})
    assert calls["n"] == 1


def test_landing_manifest_round_trip(settings: Settings) -> None:
    write_batch(
        SyntheticGenerator(settings.generation).incremental_batch(1), settings.landing_dir, "small", 42
    )
    raw = json.loads((Path(settings.landing_dir) / "b001-2026-01-31" / "_batch.json").read_text())
    batch = load_landing_batch(settings.landing_dir, "b001-2026-01-31")
    assert batch.window_start == datetime(2026, 1, 31) and raw["sequence"] == batch.sequence == 1
