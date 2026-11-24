"""Reproducible Metabase setup through its REST API.

Creates the admin user (first run only), connects the PostgreSQL warehouse with
the read-only `analytics_reader` role, and builds the "FinFlow overview"
dashboard from the native SQL questions in dashboards/metabase_questions.json.
Re-running it is safe: existing questions and dashboards with the same names
are reused.

Usage: make up-full && make demo-data && make metabase-setup
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any

import httpx

from finflow.common.config import read_env_file

ROOT = Path(__file__).resolve().parents[1]
BASE = "http://127.0.0.1:3000"
DASHBOARD = "FinFlow overview"


def wait_for_metabase(client: httpx.Client, timeout_s: int = 300) -> None:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        try:
            if client.get("/api/health").json().get("status") == "ok":
                return
        except httpx.HTTPError:
            pass
        time.sleep(3)
    sys.exit("Metabase did not become healthy in time (is `make up-full` running?)")


def login(client: httpx.Client, env: dict[str, str]) -> None:
    email, password = env["METABASE_ADMIN_EMAIL"], env["METABASE_ADMIN_PASSWORD"]
    token = client.get("/api/session/properties").json().get("setup-token")
    if token:  # first run: create the admin user
        client.post(
            "/api/setup",
            json={
                "token": token,
                "user": {"email": email, "password": password, "first_name": "FinFlow", "last_name": "Admin"},
                "prefs": {"site_name": "FinFlow (local)", "allow_tracking": False},
            },
        ).raise_for_status()
    response = client.post("/api/session", json={"username": email, "password": password})
    response.raise_for_status()
    client.headers["X-Metabase-Session"] = response.json()["id"]


def ensure_database(client: httpx.Client, env: dict[str, str]) -> int:
    for db in client.get("/api/database").json()["data"]:
        if db["name"] == "FinFlow warehouse":
            return int(db["id"])
    response = client.post(
        "/api/database",
        json={
            "engine": "postgres",
            "name": "FinFlow warehouse",
            "details": {
                "host": "warehouse-db",  # resolved inside the Docker network
                "port": 5432,
                "dbname": "warehouse",
                "user": "analytics_reader",
                "password": env["ANALYTICS_READER_PASSWORD"],
                "ssl": False,
            },
        },
    )
    response.raise_for_status()
    return int(response.json()["id"])


def ensure_card(client: httpx.Client, database_id: int, question: dict[str, Any]) -> int:
    for card in client.get("/api/card").json():
        if card["name"] == question["name"]:
            return int(card["id"])
    response = client.post(
        "/api/card",
        json={
            "name": question["name"],
            "display": question["display"],
            "visualization_settings": question.get("visualization_settings", {}),
            "dataset_query": {
                "type": "native",
                "database": database_id,
                "native": {"query": question["sql"]},
            },
        },
    )
    response.raise_for_status()
    return int(response.json()["id"])


def ensure_dashboard(client: httpx.Client, card_ids: list[int]) -> int:
    existing = [d for d in client.get("/api/dashboard").json() if d["name"] == DASHBOARD]
    if existing:
        return int(existing[0]["id"])
    dashboard = client.post("/api/dashboard", json={"name": DASHBOARD}).json()
    cards = [
        {
            "id": -(i + 1),
            "card_id": card_id,
            "row": (i // 2) * 6,
            "col": (i % 2) * 12,
            "size_x": 12,
            "size_y": 6,
        }
        for i, card_id in enumerate(card_ids)
    ]
    client.put(f"/api/dashboard/{dashboard['id']}", json={"dashcards": cards}).raise_for_status()
    return int(dashboard["id"])


def main() -> None:
    env = {**read_env_file(ROOT / ".env")}
    questions = json.loads((ROOT / "dashboards" / "metabase_questions.json").read_text())
    with httpx.Client(base_url=BASE, timeout=30) as client:
        wait_for_metabase(client)
        login(client, env)
        database_id = ensure_database(client, env)
        client.post(f"/api/database/{database_id}/sync_schema")
        card_ids = [ensure_card(client, database_id, q) for q in questions]
        dashboard_id = ensure_dashboard(client, card_ids)
    print(f"Dashboard ready: {BASE}/dashboard/{dashboard_id}")


if __name__ == "__main__":
    main()
