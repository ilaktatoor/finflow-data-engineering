# 0009 — Python 3.12, exact pins and a lockfile

Status: Accepted

## Context
The project must be reproducible on another machine and in CI, and must share
an image with Airflow, which supports a limited set of Python versions.

## Decision
- **Python 3.12** (`requires-python = ">=3.12,<3.13"`), supported by
  Airflow 3.4 and every dependency. The host where this was built had 3.14 as
  its default; `uv` provides 3.12.
- **Exact pins** for direct dependencies in `pyproject.toml`; `uv.lock` pins
  everything transitively. Docker images install from the lock
  (`uv export --frozen`).
- Versions chosen were the latest releases resolved by uv on 2026-11-24 that
  passed the test suite together: pandas 3.1.1, pyarrow 26.0.1, duckdb 2.0.1,
  pandera 0.36.0, SQLAlchemy 2.1.9, psycopg 3.3.9, FastAPI 0.165.0,
  Faker 40.63.0. Images: postgres 17.12-alpine, Airflow 3.4.0-python3.12,
  Metabase v0.65.7, MinIO RELEASE.2026-08-04 (see ADR 0002).

## Alternatives
- *Ranges (`>=`)*: easier upgrades, non-reproducible builds.
- *pip-tools / Poetry*: equivalent results; uv is faster and handles Python
  installation too.

## Consequences
Upgrades are deliberate: bump, `uv lock`, run `make check`.

## Trade-offs
Exact pins miss security fixes until someone upgrades; Dependabot (or
`uv lock --upgrade` on a schedule) is on the roadmap.
