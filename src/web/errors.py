"""Map service-layer exceptions to HTTP responses."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from src.optimization.errors import (
    DatabaseUnavailableError,
    InvalidRunRequestError,
    MissingSnapshotError,
    OptimizationServiceError,
    SolverUnavailableError,
)
from src.orchestrator.pipelines.errors import (
    InvalidPipelineRequestError,
    PipelineDatabaseError,
    PipelineDmsError,
    PipelineExecutionError,
    PipelineServiceError,
)
from src.web.jobs.lock import LockHolder


class JobConflictError(Exception):
    """Raised when the single-flight lock is already held."""

    def __init__(self, holder: LockHolder) -> None:
        self.holder = holder
        super().__init__(
            f"A {holder.kind} job is already running (job_id={holder.job_id})"
        )


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(JobConflictError)
    async def _job_conflict(_request: Request, exc: JobConflictError) -> JSONResponse:
        return JSONResponse(
            status_code=409,
            content={
                "detail": str(exc),
                "active_job_id": exc.holder.job_id,
                "active_kind": exc.holder.kind,
            },
        )

    @app.exception_handler(InvalidRunRequestError)
    @app.exception_handler(InvalidPipelineRequestError)
    async def _invalid_request(_request: Request, exc: Exception) -> JSONResponse:
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    @app.exception_handler(MissingSnapshotError)
    async def _missing_snapshot(_request: Request, exc: MissingSnapshotError) -> JSONResponse:
        return JSONResponse(status_code=409, content={"detail": str(exc)})

    @app.exception_handler(SolverUnavailableError)
    async def _solver_unavailable(
        _request: Request, exc: SolverUnavailableError
    ) -> JSONResponse:
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    @app.exception_handler(DatabaseUnavailableError)
    @app.exception_handler(PipelineDatabaseError)
    async def _database_unavailable(_request: Request, exc: Exception) -> JSONResponse:
        return JSONResponse(status_code=503, content={"detail": str(exc)})

    @app.exception_handler(PipelineDmsError)
    async def _dms_unavailable(_request: Request, exc: PipelineDmsError) -> JSONResponse:
        return JSONResponse(status_code=502, content={"detail": str(exc)})

    @app.exception_handler(PipelineExecutionError)
    @app.exception_handler(PipelineServiceError)
    @app.exception_handler(OptimizationServiceError)
    async def _service_error(_request: Request, exc: Exception) -> JSONResponse:
        return JSONResponse(status_code=500, content={"detail": str(exc)})
