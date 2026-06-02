"""On-disk extract cache for SQL-source ETL pipelines."""

from __future__ import annotations

import hashlib
import json
import shutil
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Tuple

import pandas as pd

STATUS_EXTRACTING = "EXTRACTING"
STATUS_EXTRACT_COMPLETE = "EXTRACT_COMPLETE"
MANIFEST_FILENAME = "manifest.json"


class ExtractCacheError(Exception):
    """Raised when extract cache is missing or invalid."""


def get_project_root(reference_file: Path) -> Path:
    """Locate project root by finding the sql folder."""
    current = reference_file.parent
    for _ in range(6):
        if (current / "sql").is_dir():
            return current
        current = current.parent
    return reference_file.parent.parent.parent.parent


def get_default_cache_root(reference_file: Path) -> Path:
    return get_project_root(reference_file) / "data" / "etl_cache"


def compute_extract_query_hash(
    extract_query: str,
    batch_type: str,
    since_date: Optional[date],
    snapshot_date: date,
    single_date_only: bool,
) -> str:
    parts = [
        batch_type,
        extract_query.strip(),
        since_date.isoformat() if since_date else "",
        snapshot_date.isoformat(),
        str(single_date_only),
    ]
    payload = "\n".join(parts)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class ExtractCache:
    """Manages chunked pickle extract files and a manifest per batch run."""

    def __init__(self, cache_root: Path, batch_type: str, batch_id: int) -> None:
        self.cache_root = cache_root
        self.batch_type = batch_type
        self.batch_id = batch_id
        self.batch_cache_dir = cache_root / batch_type / str(batch_id)

    @property
    def exists(self) -> bool:
        return self.batch_cache_dir.is_dir()

    def manifest_path(self) -> Path:
        return self.batch_cache_dir / MANIFEST_FILENAME

    def read_manifest(self) -> Optional[Dict[str, Any]]:
        path = self.manifest_path()
        if not path.is_file():
            return None
        with path.open(encoding="utf-8") as handle:
            return json.load(handle)

    def is_extract_complete(self, query_hash: str) -> bool:
        manifest = self.read_manifest()
        if not manifest:
            return False
        return (
            manifest.get("status") == STATUS_EXTRACT_COMPLETE
            and manifest.get("extract_query_hash") == query_hash
        )

    def clear(self) -> None:
        if self.batch_cache_dir.exists():
            shutil.rmtree(self.batch_cache_dir)

    def delete_cache(self) -> None:
        self.clear()

    def begin_extract(self, query_hash: str) -> None:
        self.clear()
        self.batch_cache_dir.mkdir(parents=True, exist_ok=True)
        self._write_manifest(
            {
                "status": STATUS_EXTRACTING,
                "extract_query_hash": query_hash,
                "batch_type": self.batch_type,
                "batch_id": self.batch_id,
                "row_count": 0,
                "column_names": [],
                "chunk_files": [],
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
        )

    def write_chunk(
        self, chunk_index: int, rows: List[tuple], columns: List[str]
    ) -> str:
        filename = f"chunk_{chunk_index:04d}.pkl"
        path = self.batch_cache_dir / filename
        df = pd.DataFrame(list(rows), columns=columns)
        df.to_pickle(path)
        return filename

    def finalize_extract(
        self,
        query_hash: str,
        chunk_files: List[str],
        row_count: int,
        column_names: List[str],
    ) -> None:
        self._write_manifest(
            {
                "status": STATUS_EXTRACT_COMPLETE,
                "extract_query_hash": query_hash,
                "batch_type": self.batch_type,
                "batch_id": self.batch_id,
                "row_count": row_count,
                "column_names": column_names,
                "chunk_files": chunk_files,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
        )

    def require_extract_complete(self, query_hash: Optional[str] = None) -> Dict[str, Any]:
        manifest = self.read_manifest()
        if not manifest:
            raise ExtractCacheError(
                f"No extract cache found for {self.batch_type} batch {self.batch_id}. "
                "Run extract first."
            )
        if manifest.get("status") != STATUS_EXTRACT_COMPLETE:
            raise ExtractCacheError(
                f"Extract cache for {self.batch_type} batch {self.batch_id} is not complete "
                f"(status={manifest.get('status')!r})."
            )
        if query_hash is not None and manifest.get("extract_query_hash") != query_hash:
            raise ExtractCacheError(
                "Extract cache does not match the current extract query. "
                "Use force_extract=True to re-query the source."
            )
        return manifest

    def iter_chunks(
        self, query_hash: Optional[str] = None
    ) -> Iterator[Tuple[List[str], List[tuple]]]:
        manifest = self.require_extract_complete(query_hash)
        column_names = manifest["column_names"]
        for chunk_file in manifest["chunk_files"]:
            chunk_path = self.batch_cache_dir / chunk_file
            if not chunk_path.is_file():
                raise ExtractCacheError(f"Missing cache chunk file: {chunk_path}")
            df = pd.read_pickle(chunk_path)
            rows = [tuple(record) for record in df.itertuples(index=False, name=None)]
            yield column_names, rows

    def _write_manifest(self, manifest: Dict[str, Any]) -> None:
        self.batch_cache_dir.mkdir(parents=True, exist_ok=True)
        with self.manifest_path().open("w", encoding="utf-8") as handle:
            json.dump(manifest, handle, indent=2)
