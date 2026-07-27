"""Typed failures exposed by the pipeline application service."""

from __future__ import annotations

from typing import Optional

from .catalog import PipelineKey


class PipelineServiceError(Exception):
    """Base class for expected pipeline service failures."""

    def __init__(
        self,
        message: str,
        *,
        pipeline: Optional[PipelineKey] = None,
        batch_id: Optional[int] = None,
    ) -> None:
        self.pipeline = pipeline
        self.batch_id = batch_id
        super().__init__(message)


class InvalidPipelineRequestError(PipelineServiceError):
    """Raised when a refresh request is invalid."""


class PipelineDatabaseError(PipelineServiceError):
    """Raised when SQL Server cannot be reached or queried."""


class PipelineDmsError(PipelineServiceError):
    """Raised when the deliveries source cannot be read."""


class PipelineExecutionError(PipelineServiceError):
    """Raised for a pipeline failure not covered by a narrower typed error."""


__all__ = [
    "InvalidPipelineRequestError",
    "PipelineDatabaseError",
    "PipelineDmsError",
    "PipelineExecutionError",
    "PipelineServiceError",
]
