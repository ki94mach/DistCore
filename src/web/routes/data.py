"""Data freshness and refresh endpoints."""

from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query

from src.web.deps import get_freshness_repository, get_job_runner, get_job_store, get_lock
from src.web.errors import JobConflictError
from src.web.schemas import JobAccepted, JobStatus, RefreshBody

router = APIRouter(tags=["data"])


def _job_status(job_id: str) -> JobStatus:
    store = get_job_store()
    try:
        meta = store.read_meta(job_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    result = store.read_result(job_id) if meta.get("status") == "succeeded" else None
    if meta.get("status") == "failed":
        result = store.read_result(job_id)
    return JobStatus(
        job_id=meta["job_id"],
        kind=meta["kind"],
        status=meta["status"],
        created_at=meta.get("created_at"),
        started_at=meta.get("started_at"),
        finished_at=meta.get("finished_at"),
        request=meta.get("request") or {},
        error=meta.get("error"),
        message=meta.get("message"),
        result=result,
    )


def _serialize_freshness(report) -> dict[str, Any]:
    return {
        "snapshot_date": report.snapshot_date.isoformat(),
        "state": report.state,
        "checked_at": report.checked_at.isoformat(),
        "pipelines": [
            {
                "pipeline": item.pipeline.value,
                "optional_for_optimize": item.optional_for_optimize,
                "expected_key": (
                    item.expected_key.isoformat() if item.expected_key else None
                ),
                "loaded_key": item.loaded_key.isoformat() if item.loaded_key else None,
                "row_count": item.row_count,
                "created_at": item.created_at.isoformat() if item.created_at else None,
                "batch_id": item.batch_id,
                "state": item.state,
                "detail": item.detail,
                "latest_batch": (
                    {
                        "batch_id": item.latest_batch.batch_id,
                        "batch_type": item.latest_batch.batch_type,
                        "status": item.latest_batch.status,
                        "started_at": (
                            item.latest_batch.started_at.isoformat()
                            if item.latest_batch.started_at
                            else None
                        ),
                        "finished_at": (
                            item.latest_batch.finished_at.isoformat()
                            if item.latest_batch.finished_at
                            else None
                        ),
                        "message": item.latest_batch.message,
                        "triggered_by": item.latest_batch.triggered_by,
                    }
                    if item.latest_batch
                    else None
                ),
            }
            for item in report.pipelines
        ],
    }


@router.get("/data/status")
def data_status(snapshot_date: date = Query(...)) -> dict[str, Any]:
    report = get_freshness_repository().get_freshness(snapshot_date)
    return _serialize_freshness(report)


@router.post("/data/refresh", response_model=JobAccepted, status_code=202)
def data_refresh(body: RefreshBody, background_tasks: BackgroundTasks) -> JobAccepted:
    store = get_job_store()
    lock = get_lock()
    runner = get_job_runner()
    request = body.model_dump(mode="json")
    job_id = store.create("refresh", request)
    holder = lock.try_acquire(job_id, "refresh")
    if holder is not None:
        store.mark_failed(job_id, f"Lock held by {holder.kind} job {holder.job_id}")
        raise JobConflictError(holder)
    background_tasks.add_task(
        runner.run_refresh,
        job_id,
        body.snapshot_date,
        body.include_deliveries,
    )
    return JobAccepted(job_id=job_id, kind="refresh", status="queued")


@router.get("/data/refresh/{job_id}", response_model=JobStatus)
def data_refresh_status(job_id: str) -> JobStatus:
    status = _job_status(job_id)
    if status.kind != "refresh":
        raise HTTPException(status_code=404, detail="Refresh job not found")
    return status


@router.get("/jobs/{job_id}", response_model=JobStatus)
def job_status(job_id: str) -> JobStatus:
    return _job_status(job_id)
