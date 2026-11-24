"""Explicit, typed configuration.

Settings come from three places, in increasing priority:

1. ``config/finflow.toml`` — behaviour shared by every environment.
2. ``.env`` in the project home — machine-specific values (never committed).
3. Real environment variables — CI, containers and one-off overrides.

Two execution modes share the same code path and differ only in adapters:

* ``lightweight`` — local filesystem lake, DuckDB warehouse, file sources. No Docker.
* ``data`` — MinIO lake, PostgreSQL warehouse, FastAPI + PostgreSQL sources.
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Literal

from finflow.common.errors import ConfigurationError

Mode = Literal["lightweight", "data"]
MODES: tuple[Mode, ...] = ("lightweight", "data")


@dataclass(frozen=True)
class ProfileSize:
    """Record counts for one generation profile."""

    customers: int
    accounts: int
    cards: int
    merchants: int
    transactions: int
    loans: int
    loan_payments: int


@dataclass(frozen=True)
class GenerationConfig:
    seed: int
    start_date: date
    history_days: int
    error_rate: float
    incremental_min_transactions: int
    incremental_max_transactions: int
    profiles: dict[str, ProfileSize]


@dataclass(frozen=True)
class QualityConfig:
    max_reject_rate: float
    warn_reject_rate: float
    max_freshness_lag_hours: int


@dataclass(frozen=True)
class RiskConfig:
    high_amount_mxn: Decimal
    velocity_max_transactions: int
    velocity_window_minutes: int
    night_start_hour: int
    night_end_hour: int


@dataclass(frozen=True)
class S3Config:
    endpoint: str
    access_key: str
    secret_key: str
    bucket: str


@dataclass(frozen=True)
class Settings:
    home: Path
    mode: Mode
    data_dir: Path
    s3: S3Config | None  # None means the lake lives on the local filesystem
    warehouse_url: str
    source_api_url: str | None
    ops_db_url: str | None
    generation: GenerationConfig
    quality: QualityConfig
    risk: RiskConfig
    log_level: str
    log_max_bytes: int
    log_backup_count: int

    @property
    def landing_dir(self) -> Path:
        """Where the simulated operational systems drop their exports."""
        return self.data_dir / "landing"

    @property
    def lake_dir(self) -> Path:
        """Local lake root (lightweight mode only)."""
        return self.data_dir / "lake"

    @property
    def reports_dir(self) -> Path:
        return self.data_dir / "reports"

    @property
    def logs_dir(self) -> Path:
        return self.data_dir / "logs"

    @property
    def sql_dir(self) -> Path:
        return self.home / "sql"


def read_env_file(path: Path) -> dict[str, str]:
    """Parse a minimal ``KEY=VALUE`` file. Comments and blank lines are ignored."""
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def _required(env: dict[str, str], key: str, mode: str) -> str:
    value = env.get(key)
    if not value:
        raise ConfigurationError(
            f"{key} is required in '{mode}' mode. Copy .env.example to .env or export it."
        )
    return value


def _load_toml(path: Path) -> dict[str, object]:
    if not path.is_file():
        raise ConfigurationError(f"Configuration file not found: {path}")
    with path.open("rb") as handle:
        return tomllib.load(handle)


def load_settings(mode: str | None = None, home: Path | None = None) -> Settings:
    """Build settings for ``mode`` (defaults to ``FINFLOW_MODE`` or ``lightweight``)."""
    home = (home or Path(os.environ.get("FINFLOW_HOME", Path.cwd()))).resolve()
    # Real environment variables win over the .env file.
    env = {**read_env_file(home / ".env"), **os.environ}

    selected = mode or env.get("FINFLOW_MODE", "lightweight")
    if selected not in MODES:
        raise ConfigurationError(f"Unknown mode '{selected}'. Expected one of {MODES}.")
    resolved_mode: Mode = "data" if selected == "data" else "lightweight"

    raw = _load_toml(Path(env.get("FINFLOW_CONFIG", home / "config" / "finflow.toml")))
    gen = raw["generation"]
    quality = raw["quality"]
    risk = raw["risk"]
    logging_cfg = raw["logging"]
    assert isinstance(gen, dict) and isinstance(quality, dict)
    assert isinstance(risk, dict) and isinstance(logging_cfg, dict)

    profiles = {name: ProfileSize(**values) for name, values in gen["profiles"].items()}
    if any(p.transactions > 10_000 for p in profiles.values()):
        raise ConfigurationError("Profiles are capped at 10,000 transactions by design.")

    data_dir = Path(env.get("FINFLOW_DATA_DIR", home / "data")).resolve()

    s3: S3Config | None = None
    if resolved_mode == "data":
        s3 = S3Config(
            endpoint=_required(env, "FINFLOW_S3_ENDPOINT", resolved_mode),
            access_key=_required(env, "FINFLOW_S3_ACCESS_KEY", resolved_mode),
            secret_key=_required(env, "FINFLOW_S3_SECRET_KEY", resolved_mode),
            bucket=env.get("FINFLOW_S3_BUCKET", "finflow-lake"),
        )
        warehouse_url = _required(env, "FINFLOW_WAREHOUSE_URL", resolved_mode)
        source_api_url: str | None = _required(env, "FINFLOW_SOURCE_API_URL", resolved_mode)
        ops_db_url: str | None = _required(env, "FINFLOW_OPS_DB_URL", resolved_mode)
    else:
        warehouse_url = env.get(
            "FINFLOW_DUCKDB_URL", f"duckdb:///{data_dir / 'warehouse' / 'finflow.duckdb'}"
        )
        source_api_url = None
        ops_db_url = None

    return Settings(
        home=home,
        mode=resolved_mode,
        data_dir=data_dir,
        s3=s3,
        warehouse_url=warehouse_url,
        source_api_url=source_api_url,
        ops_db_url=ops_db_url,
        generation=GenerationConfig(
            seed=int(gen["seed"]),
            start_date=date.fromisoformat(str(gen["start_date"])),
            history_days=int(gen["history_days"]),
            error_rate=float(gen["error_rate"]),
            incremental_min_transactions=int(gen["incremental_min_transactions"]),
            incremental_max_transactions=int(gen["incremental_max_transactions"]),
            profiles=profiles,
        ),
        quality=QualityConfig(
            max_reject_rate=float(quality["max_reject_rate"]),
            warn_reject_rate=float(quality["warn_reject_rate"]),
            max_freshness_lag_hours=int(quality["max_freshness_lag_hours"]),
        ),
        risk=RiskConfig(
            high_amount_mxn=Decimal(str(risk["high_amount_mxn"])),
            velocity_max_transactions=int(risk["velocity_max_transactions"]),
            velocity_window_minutes=int(risk["velocity_window_minutes"]),
            night_start_hour=int(risk["night_start_hour"]),
            night_end_hour=int(risk["night_end_hour"]),
        ),
        log_level=env.get("FINFLOW_LOG_LEVEL", str(logging_cfg["level"])),
        log_max_bytes=int(logging_cfg["max_bytes"]),
        log_backup_count=int(logging_cfg["backup_count"]),
    )
