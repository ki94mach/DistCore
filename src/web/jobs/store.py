"""Filesystem-backed job metadata and artifacts under data/jobs/{id}/."""

from __future__ import annotations

import json
import os
import tempfile
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Optional


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


class JobStore:
    """Create and update job directories with atomic meta.json writes."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def create(self, kind: str, request: dict[str, Any]) -> str:
        job_id = str(uuid.uuid4())
        job_dir = self.root / job_id
        job_dir.mkdir(parents=True, exist_ok=False)
        meta = {
            "job_id": job_id,
            "kind": kind,
            "status": "queued",
            "created_at": _utc_now(),
            "started_at": None,
            "finished_at": None,
            "request": request,
            "error": None,
            "message": "Queued",
            "progress": None,
        }
        self._write_meta(job_dir, meta)
        return job_id

    def mark_running(self, job_id: str, message: str = "Running") -> None:
        meta = self.read_meta(job_id)
        meta["status"] = "running"
        meta["started_at"] = _utc_now()
        meta["message"] = message
        self._write_meta(self.root / job_id, meta)

    def update_progress(
        self,
        job_id: str,
        *,
        current: int,
        total: int,
        pipeline: str,
        pipeline_name: str,
        message: str,
    ) -> None:
        """Update coarse per-pipeline progress while a refresh job is running."""
        meta = self.read_meta(job_id)
        percent = int((current - 1) / total * 100) if total > 0 else 0
        meta["progress"] = {
            "current": current,
            "total": total,
            "pipeline": pipeline,
            "pipeline_name": pipeline_name,
            "percent": percent,
            "message": message,
        }
        meta["message"] = message
        self._write_meta(self.root / job_id, meta)

    def mark_succeeded(self, job_id: str, message: str = "OK") -> None:
        meta = self.read_meta(job_id)
        meta["status"] = "succeeded"
        meta["finished_at"] = _utc_now()
        meta["message"] = message
        meta["error"] = None
        progress = meta.get("progress")
        if isinstance(progress, dict):
            progress = dict(progress)
            progress["percent"] = 100
            meta["progress"] = progress
        self._write_meta(self.root / job_id, meta)

    def mark_failed(self, job_id: str, error: str) -> None:
        meta = self.read_meta(job_id)
        meta["status"] = "failed"
        meta["finished_at"] = _utc_now()
        meta["message"] = "Failed"
        meta["error"] = error
        self._write_meta(self.root / job_id, meta)

    def write_result(self, job_id: str, payload: dict[str, Any]) -> Path:
        path = self.root / job_id / "result.json"
        path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
        return path

    def write_excel(self, job_id: str, workbook_bytes: bytes) -> Path:
        path = self.root / job_id / "result.xlsx"
        path.write_bytes(workbook_bytes)
        return path

    def excel_path(self, job_id: str) -> Path:
        return self.root / job_id / "result.xlsx"

    def result_path(self, job_id: str) -> Path:
        return self.root / job_id / "result.json"

    def read_meta(self, job_id: str) -> dict[str, Any]:
        path = self.root / job_id / "meta.json"
        if not path.exists():
            raise FileNotFoundError(f"Unknown job_id: {job_id}")
        return json.loads(path.read_text(encoding="utf-8"))

    def read_result(self, job_id: str) -> Optional[dict[str, Any]]:
        path = self.result_path(job_id)
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def mark_stale_on_startup(self) -> int:
        """Mark leftover queued/running jobs as failed after a process restart."""
        count = 0
        for meta_path in self.root.glob("*/meta.json"):
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            if meta.get("status") in {"queued", "running"}:
                meta["status"] = "failed"
                meta["finished_at"] = _utc_now()
                meta["message"] = "Failed"
                meta["error"] = "Process restarted"
                self._write_meta(meta_path.parent, meta)
                count += 1
        return count

    def _write_meta(self, job_dir: Path, meta: dict[str, Any]) -> None:
        job_dir.mkdir(parents=True, exist_ok=True)
        target = job_dir / "meta.json"
        fd, tmp_name = tempfile.mkstemp(dir=job_dir, prefix=".meta_", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(meta, handle, indent=2, default=str)
            Path(tmp_name).replace(target)
        except Exception:
            try:
                Path(tmp_name).unlink(missing_ok=True)
            except OSError:
                pass
            raise
