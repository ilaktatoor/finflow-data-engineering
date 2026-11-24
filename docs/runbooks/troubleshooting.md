# Troubleshooting

| Problem | Explanation | Fix |
|---|---|---|
| `ERROR: Landing data already exists` | `generate` will not overwrite | `finflow generate --force` or `make clean-generated` |
| `FileNotFoundError: Generate the historical batch first` | `generate-incremental` needs `b000-historical` | `finflow generate` |
| `ConfigurationError: FINFLOW_S3_ENDPOINT is required in 'data' mode` | data mode needs connection settings | `cp .env.example .env` (or `make setup`) |
| `duckdb ... Could not set lock on file` | another process (a notebook, a second CLI) has the DuckDB file open for writing | close it; notebooks should open the file with `read_only=True` |
| `uv` warns "Failed to hardlink files" | the project sits on a different filesystem than the uv cache (e.g. an external drive) | harmless; `export UV_LINK_MODE=copy` silences it |
| `docker compose` says a variable is required | `${VAR:?}` guard: `.env` missing or incomplete | `cp .env.example .env` |
| Airflow cannot write logs / `Permission denied` in `./data` | container UID differs from yours | `echo "AIRFLOW_UID=$(id -u)" >> .env`, then `make up-full` |
| Airflow or Metabase restarts repeatedly | not enough memory | close other apps; the full profile needs ~4 GB free |
| MinIO image not found | MinIO stopped publishing community images (ADR 0002) | check the pinned `pgsty/minio` tag, or build MinIO from source |
| Port already in use (5433, 5434, 8000, 8080, 3000, 9000) | another local service | change the host side of the port mapping in `docker-compose.yml` and the matching `FINFLOW_*` URL in `.env` |
| Notebook cannot find `data/` | started outside the repo root | use `make notebooks`; the first cell also `chdir`s to the root |
| `permission denied while trying to connect to the docker API` | your user cannot use the Docker socket | `sudo usermod -aG docker $USER`, then log out/in (or `newgrp docker`) |
| API returns no merchants/rates after `make clean-generated` while containers run; the batch fails the quality gate on `unknown_ref:merchant_id` / `missing_exchange_rate` | a container bind-mounted a directory that was deleted and recreated | Compose mounts `./data` (never deleted) for this reason; if you change mounts, restart the container after deleting mounted dirs |
| Bronze keeps an incomplete batch after a source outage | Bronze is write-once and the batch marker exists | `finflow --mode data clean-generated` (or delete that batch's Bronze prefix and marker), then re-ingest |
| `function round(double precision, integer) does not exist` | PostgreSQL has no `ROUND(double, int)` | cast to `NUMERIC` first (as the CLI does) |
| Unpausing the daily DAG produced two batches | the scheduler created a run for the latest interval, plus your manual trigger | expected; trigger manually *or* unpause, not both |
| Numbers in docs differ from your run | timings vary by machine; counts do not | counts are deterministic for the same seed and profile; timings are not |
