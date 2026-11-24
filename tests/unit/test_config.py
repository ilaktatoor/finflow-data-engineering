from pathlib import Path

import pytest

from finflow.common.config import load_settings, read_env_file
from finflow.common.errors import ConfigurationError

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_lightweight_defaults(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FINFLOW_DATA_DIR", str(tmp_path))
    settings = load_settings("lightweight", home=REPO_ROOT)
    assert settings.s3 is None
    assert settings.warehouse_url == f"duckdb:///{tmp_path / 'warehouse' / 'finflow.duckdb'}"
    assert settings.generation.profiles["small"].transactions == 2000


def test_data_mode_requires_explicit_connection_settings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for key in (
        "FINFLOW_S3_ENDPOINT",
        "FINFLOW_S3_ACCESS_KEY",
        "FINFLOW_S3_SECRET_KEY",
        "FINFLOW_WAREHOUSE_URL",
        "FINFLOW_SOURCE_API_URL",
        "FINFLOW_OPS_DB_URL",
    ):
        monkeypatch.delenv(key, raising=False)
    home = tmp_path / "home"
    (home / "config").mkdir(parents=True)
    (home / "config" / "finflow.toml").write_text((REPO_ROOT / "config" / "finflow.toml").read_text())
    with pytest.raises(ConfigurationError, match="FINFLOW_S3_ENDPOINT"):
        load_settings("data", home=home)


def test_unknown_mode() -> None:
    with pytest.raises(ConfigurationError, match="Unknown mode"):
        load_settings("cloud", home=REPO_ROOT)


def test_env_file_parsing(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text("# comment\nA=1\nB = 'two'\n\nINVALID\nC=\"x=y\"\n")
    assert read_env_file(env) == {"A": "1", "B": "two", "C": "x=y"}
