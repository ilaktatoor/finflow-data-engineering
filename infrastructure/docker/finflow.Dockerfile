# FinFlow application image: the CLI and the FastAPI source simulator.
# Dependencies are installed from uv.lock, so the image matches local development.
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    FINFLOW_HOME=/opt/finflow \
    FINFLOW_DATA_DIR=/opt/finflow/data

COPY --from=ghcr.io/astral-sh/uv:0.13.6 /uv /usr/local/bin/uv

WORKDIR /opt/finflow
COPY pyproject.toml uv.lock README.md ./
RUN uv export --frozen --no-dev --no-emit-project --format requirements.txt -o /tmp/requirements.txt \
    && uv pip install --system --no-cache -r /tmp/requirements.txt

COPY src ./src
COPY sql ./sql
COPY config ./config
RUN uv pip install --system --no-cache --no-deps . \
    && useradd --uid 10001 --create-home finflow \
    && mkdir -p /opt/finflow/data && chown finflow /opt/finflow/data

USER finflow
EXPOSE 8000
CMD ["finflow", "serve-api", "--host", "0.0.0.0", "--port", "8000"]
