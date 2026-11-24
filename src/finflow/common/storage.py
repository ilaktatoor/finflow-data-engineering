"""Lake storage on top of ``pyarrow.fs``.

One class covers both execution modes because PyArrow already abstracts the
filesystem: ``LocalFileSystem`` in lightweight mode and ``S3FileSystem`` pointed
at MinIO in data mode. Paths are always relative to the lake root
(a local directory or an S3 bucket).
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

import pandas as pd
import pyarrow as pa
import pyarrow.fs as pafs
import pyarrow.parquet as pq

from finflow.common.config import Settings


@dataclass
class LakeStorage:
    fs: pafs.FileSystem
    root: str  # absolute local directory or bucket name

    @classmethod
    def from_settings(cls, settings: Settings) -> LakeStorage:
        if settings.s3 is None:
            settings.lake_dir.mkdir(parents=True, exist_ok=True)
            return cls(pafs.LocalFileSystem(), str(settings.lake_dir))
        endpoint = urlparse(settings.s3.endpoint)
        fs = pafs.S3FileSystem(
            access_key=settings.s3.access_key,
            secret_key=settings.s3.secret_key,
            endpoint_override=endpoint.netloc,
            scheme=endpoint.scheme or "http",
            region="us-east-1",  # MinIO ignores it, PyArrow requires one
            allow_bucket_creation=True,  # first run creates the lake bucket
            allow_bucket_deletion=True,  # `clean-generated` and test teardown remove it
        )
        storage = cls(fs, settings.s3.bucket)
        storage.ensure_root()
        return storage

    @classmethod
    def local(cls, root: Path) -> LakeStorage:
        root.mkdir(parents=True, exist_ok=True)
        return cls(pafs.LocalFileSystem(), str(root))

    def ensure_root(self) -> None:
        if self.fs.get_file_info(self.root).type == pafs.FileType.NotFound:
            self.fs.create_dir(self.root)

    def _full(self, path: str) -> str:
        return f"{self.root}/{path.lstrip('/')}"

    @property
    def is_local(self) -> bool:
        return isinstance(self.fs, pafs.LocalFileSystem)

    def exists(self, path: str) -> bool:
        return self.fs.get_file_info(self._full(path)).type != pafs.FileType.NotFound

    def write_bytes(self, path: str, data: bytes) -> None:
        full = self._full(path)
        self.fs.create_dir(full.rsplit("/", 1)[0], recursive=True)
        with self.fs.open_output_stream(full) as out:
            out.write(data)

    def read_bytes(self, path: str) -> bytes:
        with self.fs.open_input_stream(self._full(path)) as stream:
            data: bytes = stream.read()
            return data

    def list_files(self, prefix: str) -> list[str]:
        """Relative paths of every file under ``prefix`` (recursive, sorted)."""
        selector = pafs.FileSelector(self._full(prefix), recursive=True, allow_not_found=True)
        offset = len(self.root) + 1
        return sorted(
            info.path[offset:] for info in self.fs.get_file_info(selector) if info.type == pafs.FileType.File
        )

    def write_parquet(self, df: pd.DataFrame, path: str) -> None:
        table = pa.Table.from_pandas(df, preserve_index=False)
        buffer = io.BytesIO()
        pq.write_table(table, buffer, compression="zstd")
        self.write_bytes(path, buffer.getvalue())

    def read_parquet(self, paths: list[str], columns: list[str] | None = None) -> pd.DataFrame:
        """Read and concatenate Parquet files.

        Files are read one by one and unified with ``promote_options="permissive"``
        because a column that is entirely null in one batch is typed ``null`` there.
        """
        if not paths:
            return pd.DataFrame(columns=columns) if columns else pd.DataFrame()
        tables = [pq.read_table(self._full(p), filesystem=self.fs, columns=columns) for p in paths]
        return pa.concat_tables(tables, promote_options="permissive").to_pandas()

    def delete_file(self, path: str) -> None:
        self.fs.delete_file(self._full(path))

    def delete_dir(self, prefix: str) -> None:
        if self.exists(prefix):
            self.fs.delete_dir(self._full(prefix))
