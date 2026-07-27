"""Non-interactive application service for ETL snapshot refreshes."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Callable, Mapping, Optional

import pyodbc
import requests

from .catalog import (
    PIPELINE_CATALOG,
    PIPELINES_BY_KEY,
    PipelineDefinition,
    PipelineKey,
    get_pipeline_definition,
)
from .errors import (
    InvalidPipelineRequestError,
    PipelineDatabaseError,
    PipelineDmsError,
    PipelineExecutionError,
    PipelineServiceError,
)


@dataclass(frozen=True)
class RefreshRequest:
    pipeline: PipelineKey
    snapshot_date: date
    triggered_by: str = "WEB_UI"


@dataclass(frozen=True)
class RefreshAllRequest:
    snapshot_date: date
    include_deliveries: bool = True
    triggered_by: str = "WEB_UI"


@dataclass(frozen=True)
class PipelineRefreshResult:
    pipeline: PipelineKey
    batch_type: str
    snapshot_date: date
    batch_id: Optional[int]
    status: str
    message: str


@dataclass(frozen=True)
class RefreshAllResult:
    snapshot_date: date
    results: tuple[PipelineRefreshResult, ...]
    succeeded: tuple[PipelineKey, ...]
    failed: tuple[PipelineKey, ...]

    @property
    def is_successful(self) -> bool:
        return not self.failed


class PipelineService:
    """Run existing pipelines without terminal, VPN, or web dependencies."""

    def __init__(
        self,
        connection_factory,
        database_type: str = "prod",
        *,
        pipeline_factories: Optional[Mapping[PipelineKey, Callable[..., object]]] = None,
    ) -> None:
        self._connection_factory = connection_factory
        self._database_type = database_type
        self._pipeline_factories = {
            definition.key: definition.pipeline_class
            for definition in PIPELINE_CATALOG
        }
        if pipeline_factories:
            self._pipeline_factories.update(pipeline_factories)

    def refresh_one(self, request: RefreshRequest) -> PipelineRefreshResult:
        key = self._validate_request(request.pipeline, request.triggered_by)
        definition = get_pipeline_definition(key)
        factory = self._pipeline_factories.get(key)
        if factory is None:
            raise InvalidPipelineRequestError(
                f"No runner is configured for pipeline '{key.value}'",
                pipeline=key,
            )

        pipeline = None
        try:
            kwargs = {
                "batch_id": None,
                "snapshot_date": request.snapshot_date,
                "connection_factory": self._connection_factory,
                "database_type": self._database_type,
                "triggered_by": request.triggered_by,
                "log_fn": None,
            }
            if definition.optional_for_optimize:
                kwargs["show_progress"] = False
            pipeline = factory(**kwargs)
            pipeline.run()
            batch_id = self._batch_id(pipeline)
            return PipelineRefreshResult(
                pipeline=key,
                batch_type=definition.batch_type,
                snapshot_date=request.snapshot_date,
                batch_id=batch_id,
                status="SUCCESS",
                message="OK",
            )
        except KeyboardInterrupt:
            raise
        except PipelineServiceError:
            raise
        except (pyodbc.Error, ConnectionError, TimeoutError) as exc:
            raise PipelineDatabaseError(
                f"Database operation failed for {definition.name}: {exc}",
                pipeline=key,
                batch_id=self._batch_id(pipeline),
            ) from exc
        except (
            requests.RequestException,
            OSError,
            ImportError,
            FileNotFoundError,
            ValueError,
        ) as exc:
            if definition.optional_for_optimize:
                raise PipelineDmsError(
                    f"DMS delivery refresh failed: {exc}",
                    pipeline=key,
                    batch_id=self._batch_id(pipeline),
                ) from exc
            raise PipelineExecutionError(
                f"{definition.name} refresh failed: {exc}",
                pipeline=key,
                batch_id=self._batch_id(pipeline),
            ) from exc
        except Exception as exc:
            raise PipelineExecutionError(
                f"{definition.name} refresh failed: {exc}",
                pipeline=key,
                batch_id=self._batch_id(pipeline),
            ) from exc

    def refresh_all(
        self,
        request: RefreshAllRequest,
        *,
        on_progress: Optional[
            Callable[[int, int, PipelineDefinition], None]
        ] = None,
    ) -> RefreshAllResult:
        self._validate_request(PipelineKey.FACTORY_INVENTORY, request.triggered_by)
        results: list[PipelineRefreshResult] = []
        succeeded: list[PipelineKey] = []
        failed: list[PipelineKey] = []

        definitions = [
            definition
            for definition in PIPELINE_CATALOG
            if not (
                definition.optional_for_optimize and not request.include_deliveries
            )
        ]
        total = len(definitions)

        for index, definition in enumerate(definitions, start=1):
            if on_progress is not None:
                on_progress(index, total, definition)
            try:
                result = self.refresh_one(
                    RefreshRequest(
                        pipeline=definition.key,
                        snapshot_date=request.snapshot_date,
                        triggered_by=request.triggered_by,
                    )
                )
                succeeded.append(definition.key)
            except PipelineServiceError as exc:
                result = PipelineRefreshResult(
                    pipeline=definition.key,
                    batch_type=definition.batch_type,
                    snapshot_date=request.snapshot_date,
                    batch_id=exc.batch_id,
                    status="FAILED",
                    message=str(exc),
                )
                failed.append(definition.key)
            results.append(result)

        return RefreshAllResult(
            snapshot_date=request.snapshot_date,
            results=tuple(results),
            succeeded=tuple(succeeded),
            failed=tuple(failed),
        )

    @staticmethod
    def _validate_request(pipeline, triggered_by: str) -> PipelineKey:
        try:
            key = pipeline if isinstance(pipeline, PipelineKey) else PipelineKey(pipeline)
        except (TypeError, ValueError) as exc:
            raise InvalidPipelineRequestError(
                f"Unknown pipeline: {pipeline}"
            ) from exc
        if not triggered_by or not triggered_by.strip():
            raise InvalidPipelineRequestError(
                "triggered_by must not be empty", pipeline=key
            )
        if key not in PIPELINES_BY_KEY:
            raise InvalidPipelineRequestError(
                f"Unknown pipeline: {key}", pipeline=key
            )
        return key

    @staticmethod
    def _batch_id(pipeline) -> Optional[int]:
        value = getattr(pipeline, "batch_id", None) if pipeline is not None else None
        return int(value) if value else None


__all__ = [
    "PipelineRefreshResult",
    "PipelineService",
    "RefreshAllRequest",
    "RefreshAllResult",
    "RefreshRequest",
]
