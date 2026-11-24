"""Structured JSON logging with batch and run context.

Every record carries ``run_id`` and ``batch_id`` from context variables, so a
single ``grep`` on a batch id reconstructs everything that happened to it.
"""

from __future__ import annotations

import json
import logging
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import UTC, datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

run_id_var: ContextVar[str | None] = ContextVar("run_id", default=None)
batch_id_var: ContextVar[str | None] = ContextVar("batch_id", default=None)

_RESERVED = set(vars(logging.makeLogRecord({})).keys()) | {"message", "asctime"}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
            "run_id": run_id_var.get(),
            "batch_id": batch_id_var.get(),
        }
        # Anything passed through `extra=` becomes a structured field.
        payload.update({k: v for k, v in vars(record).items() if k not in _RESERVED})
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def configure_logging(level: str, log_dir: Path | None, max_bytes: int, backup_count: int) -> None:
    """Send JSON logs to stderr and, optionally, to a size-rotated file."""
    root = logging.getLogger("finflow")
    root.handlers.clear()
    root.setLevel(level)
    root.propagate = False
    formatter = JsonFormatter()

    stream = logging.StreamHandler(sys.stderr)
    stream.setFormatter(formatter)
    root.addHandler(stream)

    if log_dir is not None:
        log_dir.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(
            log_dir / "finflow.log", maxBytes=max_bytes, backupCount=backup_count
        )
        file_handler.setFormatter(formatter)
        root.addHandler(file_handler)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(f"finflow.{name}")


@contextmanager
def log_context(*, run_id: str | None = None, batch_id: str | None = None) -> Iterator[None]:
    """Bind run/batch identifiers to every log record emitted inside the block."""
    tokens = []
    if run_id is not None:
        tokens.append((run_id_var, run_id_var.set(run_id)))
    if batch_id is not None:
        tokens.append((batch_id_var, batch_id_var.set(batch_id)))
    try:
        yield
    finally:
        for var, token in reversed(tokens):
            var.reset(token)
