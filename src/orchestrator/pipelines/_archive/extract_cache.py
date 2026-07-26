"""On-disk extract cache for SQL-source ETL pipelines."""

from __future__ import annotations

import hashlib
import json
import shutil
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

STATUS_EXTRACTING = "EXTRACTING"
STATUS_EXTRACT_COMPLETE = "EXTRACT_COMPLETE"
VERIFIED_SOURCE_CACHE = "source_cache"
VERIFIED_STAGING = "staging"
MANIFEST_FILENAME = "manifest.json"
EXTRACT_FILENAME = "extract.pkl"


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
    """Manages a single-file extract cache and manifest per batch run."""

    def __init__(self, cache_root: Path, batch_type: str, batch_id: int) -> None:
        self.cache_root = cache_root
        self.batch_type = batch_type
        self.batch_id = batch_id
        self.batch_cache_dir = cache_root / batch_type / str(batch_id)

    @property
    def exists(self) -> bool:
        return self.batch_cache_dir.is_dir()

    @property
    def extract_path(self) -> Path:
        return self.batch_cache_dir / EXTRACT_FILENAME

    def manifest_path(self) -> Path:
        return self.batch_cache_dir / MANIFEST_FILENAME

    def read_manifest(self) -> Optional[Dict[str, Any]]:
        path = self.manifest_path()
        if not path.is_file():
            return None
        with path.open(encoding="utf-8") as handle:
            return json.load(handle)

    def is_extract_complete(self, query_hash: str) -> bool:
        """True when extract.pkl is written for the current query (may be unverified)."""
        manifest = self.read_manifest()
        if not manifest:
            return False
        return (
            manifest.get("status") == STATUS_EXTRACT_COMPLETE
            and manifest.get("extract_query_hash") == query_hash
            and self.extract_path.is_file()
        )

    def is_source_cache_verified(self, query_hash: str) -> bool:
        manifest = self.read_manifest()
        if not manifest:
            return False
        step = manifest.get("last_verified_step")
        return (
            manifest.get("status") == STATUS_EXTRACT_COMPLETE
            and manifest.get("extract_query_hash") == query_hash
            and step in (VERIFIED_SOURCE_CACHE, VERIFIED_STAGING)
            and self.extract_path.is_file()
        )

    def is_staging_verified(self, query_hash: str) -> bool:
        manifest = self.read_manifest()
        if not manifest:
            return False
        return (
            manifest.get("extract_query_hash") == query_hash
            and manifest.get("last_verified_step") == VERIFIED_STAGING
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
                "source_row_count": None,
                "last_verified_step": None,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
        )

    def write_extract(self, df: pd.DataFrame, query_hash: str) -> None:
        """Write a single extract.pkl and finalize manifest metadata."""
        self.batch_cache_dir.mkdir(parents=True, exist_ok=True)
        df.to_pickle(self.extract_path)
        column_names = [str(col) for col in df.columns]
        self._write_manifest(
            {
                "status": STATUS_EXTRACT_COMPLETE,
                "extract_query_hash": query_hash,
                "batch_type": self.batch_type,
                "batch_id": self.batch_id,
                "row_count": len(df),
                "column_names": column_names,
                "source_row_count": None,
                "last_verified_step": None,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
        )

    def read_extract(self, query_hash: Optional[str] = None) -> pd.DataFrame:
        manifest = self.require_extract_complete(query_hash)
        if not self.extract_path.is_file():
            raise ExtractCacheError(f"Missing extract file: {self.extract_path}")
        df = pd.read_pickle(self.extract_path)
        expected = manifest.get("row_count", -1)
        if len(df) != expected:
            raise ExtractCacheError(
                f"Cache row count mismatch: manifest={expected}, extract.pkl={len(df)}"
            )
        return df

    def get_manifest_row_count(self, query_hash: Optional[str] = None) -> int:
        manifest = self.require_extract_complete(query_hash)
        return int(manifest["row_count"])

    def set_verified_step(
        self,
        step: str,
        *,
        source_row_count: Optional[int] = None,
    ) -> None:
        manifest = self.read_manifest()
        if not manifest:
            raise ExtractCacheError("Cannot set verified step: manifest missing.")
        manifest["last_verified_step"] = step
        if source_row_count is not None:
            manifest["source_row_count"] = source_row_count
        self._write_manifest(manifest)

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
        if not self.extract_path.is_file():
            raise ExtractCacheError(f"Missing extract file: {self.extract_path}")
        return manifest

    def require_source_cache_verified(self, query_hash: str) -> Dict[str, Any]:
        manifest = self.require_extract_complete(query_hash)
        if manifest.get("last_verified_step") not in (VERIFIED_SOURCE_CACHE, VERIFIED_STAGING):
            raise ExtractCacheError(
                f"Extract cache for {self.batch_type} batch {self.batch_id} is not "
                "source-verified. Run extract first."
            )
        return manifest

    def _write_manifest(self, manifest: Dict[str, Any]) -> None:
        self.batch_cache_dir.mkdir(parents=True, exist_ok=True)
        with self.manifest_path().open("w", encoding="utf-8") as handle:
            json.dump(manifest, handle, indent=2)
