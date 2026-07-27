"""Typed failures exposed by the optimization service boundary."""

from __future__ import annotations

from datetime import date
from typing import Optional


class OptimizationServiceError(Exception):
    """Base class for expected optimization service failures."""


class InvalidRunRequestError(OptimizationServiceError):
    """Raised when a run request contains conflicting or invalid values."""


class MissingSnapshotError(OptimizationServiceError):
    """Raised when data required for the requested snapshot is unavailable."""

    def __init__(self, snapshot_date: date, message: Optional[str] = None) -> None:
        self.snapshot_date = snapshot_date
        super().__init__(
            message or f"Required optimization snapshot data is missing for {snapshot_date!s}"
        )


class SolverUnavailableError(OptimizationServiceError):
    """Raised when the requested solver is unknown or cannot run."""

    def __init__(self, solver: str, message: Optional[str] = None) -> None:
        self.solver = solver
        super().__init__(message or f"Solver '{solver}' is unavailable")


class DatabaseUnavailableError(OptimizationServiceError):
    """Raised when SQL Server cannot be reached while loading a run."""

