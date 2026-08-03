"""Shared dependency wiring for the web MVP."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

import pyodbc

from src.optimization.service import OptimizationService
from src.orchestrator.health.db_health import DatabaseHealthChecker
from src.orchestrator.pipelines.freshness import SnapshotFreshnessRepository
from src.orchestrator.pipelines.service import PipelineService
from src.orchestrator.services.sql_server_db import DBConnectionFactory, SQLExecutor
from src.web.jobs.lock import SingleFlightLock
from src.web.jobs.runner import JobRunner
from src.web.jobs.store import JobStore

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_JOBS_ROOT = _PROJECT_ROOT / "data" / "jobs"

_factory: Optional[DBConnectionFactory] = None
_job_store: Optional[JobStore] = None
_lock: Optional[SingleFlightLock] = None
_job_runner: Optional[JobRunner] = None


def disable_odbc_pooling() -> None:
    """Disable pyodbc driver-manager pooling for the low-traffic web process."""
    pyodbc.pooling = False


def get_project_root() -> Path:
    return _PROJECT_ROOT


def resolve_db_config_path() -> Optional[Path]:
    """Return DISTCORE_DB_CONFIG path when set, else None (use factory default)."""
    raw = os.environ.get("DISTCORE_DB_CONFIG", "").strip()
    if not raw:
        return None
    return Path(raw).expanduser().resolve()


def resolve_jobs_root() -> Path:
    """Jobs directory: DISTCORE_JOBS_DIR or {repo}/data/jobs."""
    raw = os.environ.get("DISTCORE_JOBS_DIR", "").strip()
    if raw:
        return Path(raw).expanduser().resolve()
    return _DEFAULT_JOBS_ROOT


def resolve_bind_host() -> str:
    return os.environ.get("DISTCORE_HOST", "0.0.0.0").strip() or "0.0.0.0"


def resolve_bind_port() -> int:
    raw = os.environ.get("DISTCORE_PORT", "8000").strip() or "8000"
    return int(raw)


def get_connection_factory() -> DBConnectionFactory:
    global _factory
    if _factory is None:
        disable_odbc_pooling()
        config_path = resolve_db_config_path()
        if config_path is not None:
            _factory = DBConnectionFactory.from_config_file(
                config_path,
                use_pool=False,
            )
        else:
            _factory = DBConnectionFactory(use_pool=False)
    return _factory


def get_sql_executor() -> SQLExecutor:
    return SQLExecutor(get_connection_factory())


def get_pipeline_service() -> PipelineService:
    return PipelineService(get_connection_factory(), database_type="prod")


def get_freshness_repository() -> SnapshotFreshnessRepository:
    return SnapshotFreshnessRepository(get_connection_factory(), database_type="prod")


def get_optimization_service() -> OptimizationService:
    return OptimizationService(get_sql_executor(), database_type="prod")


def get_health_checker() -> DatabaseHealthChecker:
    return DatabaseHealthChecker(get_connection_factory())


def close_runtime_connections() -> None:
    """Close any factory-managed pooled connections without creating a factory."""
    if _factory is not None:
        _factory.close_all_connections()


def get_job_store(root: Optional[Path] = None) -> JobStore:
    global _job_store
    if _job_store is None:
        _job_store = JobStore(root or resolve_jobs_root())
    return _job_store


def get_lock() -> SingleFlightLock:
    global _lock
    if _lock is None:
        _lock = SingleFlightLock()
    return _lock


def get_job_runner() -> JobRunner:
    global _job_runner
    if _job_runner is None:
        _job_runner = JobRunner(
            get_job_store(),
            get_lock(),
            pipeline_service_factory=get_pipeline_service,
            optimization_service_factory=get_optimization_service,
        )
    return _job_runner


def reset_runtime_singletons(
    *,
    job_store: Optional[JobStore] = None,
    lock: Optional[SingleFlightLock] = None,
    job_runner: Optional[JobRunner] = None,
    factory: Optional[DBConnectionFactory] = None,
) -> None:
    """Test helper to replace process-wide singletons."""
    global _job_store, _lock, _job_runner, _factory
    _job_store = job_store
    _lock = lock
    _job_runner = job_runner
    _factory = factory
