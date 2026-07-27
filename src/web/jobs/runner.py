"""Background job runners for refresh and optimize."""

from __future__ import annotations

from datetime import date
from typing import Any, Callable, Optional

from src.optimization.data import OptimizationSettings
from src.optimization.export import ExportRequestMeta, write_optimization_xlsx
from src.optimization.service import OptimizationService, RunRequest, RunResult
from src.orchestrator.pipelines.service import (
    PipelineService,
    RefreshAllRequest,
    RefreshAllResult,
)
from src.web.jobs.lock import SingleFlightLock
from src.web.jobs.store import JobStore


def serialize_refresh_result(result: RefreshAllResult) -> dict[str, Any]:
    return {
        "snapshot_date": result.snapshot_date.isoformat(),
        "succeeded": [item.value for item in result.succeeded],
        "failed": [item.value for item in result.failed],
        "is_successful": result.is_successful,
        "results": [
            {
                "pipeline": item.pipeline.value,
                "batch_type": item.batch_type,
                "snapshot_date": item.snapshot_date.isoformat(),
                "batch_id": item.batch_id,
                "status": item.status,
                "message": item.message,
            }
            for item in result.results
        ],
    }


def serialize_optimize_result(result: RunResult) -> dict[str, Any]:
    payload = result.to_dict()
    payload["shipments_full"] = [
        {
            "distributor_id": item.distributor_id,
            "distributor_name": item.distributor_name,
            "product_id": item.product_id,
            "product_name": item.product_name,
            "product_name_en": item.product_name_en,
            "quantity": item.quantity,
        }
        for item in result.shipments
    ]
    payload["table"] = {
        "columns": list(result.table.columns),
        "rows": [dict(row) for row in result.table.rows],
    }
    return payload


class JobRunner:
    """Execute refresh/optimize work while holding the single-flight lock."""

    def __init__(
        self,
        store: JobStore,
        lock: SingleFlightLock,
        *,
        pipeline_service_factory: Callable[[], PipelineService],
        optimization_service_factory: Callable[[], OptimizationService],
    ) -> None:
        self._store = store
        self._lock = lock
        self._pipeline_service_factory = pipeline_service_factory
        self._optimization_service_factory = optimization_service_factory

    def run_refresh(
        self,
        job_id: str,
        snapshot_date: date,
        include_deliveries: bool,
    ) -> None:
        try:
            self._store.mark_running(job_id, "Refreshing snapshots")
            service = self._pipeline_service_factory()
            result = service.refresh_all(
                RefreshAllRequest(
                    snapshot_date=snapshot_date,
                    include_deliveries=include_deliveries,
                    triggered_by="WEB_UI",
                )
            )
            self._store.write_result(job_id, serialize_refresh_result(result))
            if result.is_successful:
                self._store.mark_succeeded(job_id, "Refresh completed")
            else:
                failed = ", ".join(item.value for item in result.failed)
                self._store.mark_failed(job_id, f"Refresh partially failed: {failed}")
        except Exception as exc:
            self._store.mark_failed(job_id, str(exc))
        finally:
            self._lock.release(job_id)

    def run_optimize(
        self,
        job_id: str,
        snapshot_date: date,
        solver: str,
        settings: Optional[OptimizationSettings],
        settings_preset: Optional[str],
        solver_options: Optional[dict[str, dict[str, Any]]],
        include_export_variables: bool,
    ) -> None:
        try:
            self._store.mark_running(job_id, "Running optimization")
            service = self._optimization_service_factory()
            result = service.run(
                RunRequest(
                    snapshot_date=snapshot_date,
                    solver=solver,
                    settings=settings,
                    settings_preset=settings_preset,
                    solver_options=solver_options,
                    include_export_variables=include_export_variables,
                )
            )
            self._store.write_result(job_id, serialize_optimize_result(result))
            write_optimization_xlsx(
                result,
                self._store.excel_path(job_id),
                request=ExportRequestMeta(
                    snapshot_date=snapshot_date,
                    solver=solver,
                    settings=settings,
                    settings_preset=settings_preset,
                    solver_options=solver_options,
                    include_export_variables=include_export_variables,
                ),
            )
            self._store.mark_succeeded(job_id, "Optimization completed")
        except Exception as exc:
            self._store.mark_failed(job_id, str(exc))
        finally:
            self._lock.release(job_id)
