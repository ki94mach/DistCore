"""Optimization submit, poll, and Excel download endpoints."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, BackgroundTasks, HTTPException
from fastapi.responses import FileResponse

from src.optimization.export import download_filename
from src.web.deps import get_job_runner, get_job_store, get_lock
from src.web.errors import JobConflictError
from src.web.routes.data import _job_status
from src.web.schemas import JobAccepted, JobStatus, OptimizeBody

router = APIRouter(tags=["optimizations"])


@router.post("/optimizations", response_model=JobAccepted, status_code=202)
def start_optimization(
    body: OptimizeBody, background_tasks: BackgroundTasks
) -> JobAccepted:
    store = get_job_store()
    lock = get_lock()
    runner = get_job_runner()
    request = body.model_dump(mode="json")
    job_id = store.create("optimize", request)
    holder = lock.try_acquire(job_id, "optimize")
    if holder is not None:
        store.mark_failed(job_id, f"Lock held by {holder.kind} job {holder.job_id}")
        raise JobConflictError(holder)

    settings = body.settings.to_dataclass() if body.settings is not None else None
    background_tasks.add_task(
        runner.run_optimize,
        job_id,
        body.snapshot_date,
        body.solver,
        settings,
        body.settings_preset,
        body.solver_options,
        body.include_export_variables,
    )
    return JobAccepted(job_id=job_id, kind="optimize", status="queued")


@router.get("/optimizations/{job_id}", response_model=JobStatus)
def optimization_status(job_id: str) -> JobStatus:
    status = _job_status(job_id)
    if status.kind != "optimize":
        raise HTTPException(status_code=404, detail="Optimization job not found")
    return status


@router.get("/optimizations/{job_id}/download")
def optimization_download(job_id: str) -> FileResponse:
    store = get_job_store()
    try:
        meta = store.read_meta(job_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if meta.get("kind") != "optimize":
        raise HTTPException(status_code=404, detail="Optimization job not found")
    if meta.get("status") != "succeeded":
        raise HTTPException(
            status_code=404,
            detail=f"Excel not ready (status={meta.get('status')})",
        )
    path = store.excel_path(job_id)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Excel file missing")

    request = meta.get("request") or {}
    snapshot_raw = request.get("snapshot_date")
    solver = str(request.get("solver") or "solver")
    try:
        snapshot_date = (
            date.fromisoformat(snapshot_raw)
            if isinstance(snapshot_raw, str)
            else date.today()
        )
    except ValueError:
        snapshot_date = date.today()

    return FileResponse(
        path,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=download_filename(snapshot_date, solver),
    )
