"""Health endpoint."""

from __future__ import annotations

from fastapi import APIRouter

from src.web.deps import get_health_checker
from src.web.schemas import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return _database_health()


@router.get("/ready", response_model=HealthResponse)
def ready() -> HealthResponse:
    return _database_health()


@router.get("/live", response_model=HealthResponse)
def live() -> HealthResponse:
    return HealthResponse(status="ok")


def _database_health() -> HealthResponse:
    checker = get_health_checker()
    try:
        database = checker.check_health(database_type="prod", timeout=5.0)
    except Exception as exc:
        database = {
            "status": "unhealthy",
            "database_type": "prod",
            "error": str(exc),
        }
    status = "ok" if database.get("status") == "healthy" else "degraded"
    return HealthResponse(status=status, database=database)
