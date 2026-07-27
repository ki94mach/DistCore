"""Snapshot freshness and optimization readiness queries."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any, Optional

from .catalog import (
    BusinessKeyType,
    PIPELINE_CATALOG,
    PipelineDefinition,
    PipelineKey,
)


@dataclass(frozen=True)
class BatchRunInfo:
    batch_id: int
    batch_type: str
    status: str
    started_at: Optional[datetime]
    finished_at: Optional[datetime]
    message: Optional[str]
    triggered_by: Optional[str]


@dataclass(frozen=True)
class PipelineFreshness:
    pipeline: PipelineKey
    optional_for_optimize: bool
    expected_key: Optional[date]
    loaded_key: Optional[date]
    row_count: int
    created_at: Optional[datetime]
    batch_id: Optional[int]
    latest_batch: Optional[BatchRunInfo]
    state: str
    detail: str


@dataclass(frozen=True)
class FreshnessReport:
    snapshot_date: date
    state: str
    pipelines: tuple[PipelineFreshness, ...]
    checked_at: datetime


class SnapshotFreshnessRepository:
    """Read current snapshot freshness and derive readiness for optimization."""

    def __init__(self, connection_factory, database_type: str = "prod") -> None:
        self._connection_factory = connection_factory
        self._database_type = database_type

    def get_freshness(self, snapshot_date: date) -> FreshnessReport:
        sales_month = self._resolve_sales_snapshot_month(snapshot_date)
        target_year, target_month = self._resolve_jalali_year_month(snapshot_date)
        rows: list[PipelineFreshness] = []
        required_states: list[str] = []

        for definition in PIPELINE_CATALOG:
            expected_key = (
                sales_month
                if definition.business_key_type == BusinessKeyType.SNAPSHOT_MONTH
                else snapshot_date
            )
            summary = self._read_snapshot_summary(
                definition, snapshot_date, sales_month, target_year, target_month
            )
            latest_batch = self._latest_batch(definition.batch_type)
            freshness = self._classify(definition, expected_key, summary, latest_batch)
            rows.append(freshness)
            if not definition.optional_for_optimize:
                required_states.append(freshness.state)

        return FreshnessReport(
            snapshot_date=snapshot_date,
            state=self._overall_state(required_states),
            pipelines=tuple(rows),
            checked_at=datetime.now(UTC),
        )

    def _read_snapshot_summary(
        self,
        definition: PipelineDefinition,
        snapshot_date: date,
        sales_month: date,
        target_year: int,
        target_month: int,
    ) -> dict[str, Any]:
        table = self._connection_factory.qualify(
            definition.snapshot_table, self._database_type
        )

        if definition.key == PipelineKey.TARGET:
            query = f"""
                SELECT
                    COUNT(*) AS row_count,
                    MAX(snapshot_date) AS loaded_key,
                    MAX(created_at) AS created_at,
                    MAX(batch_id) AS batch_id,
                    COUNT(DISTINCT batch_id) AS distinct_batch_ids
                FROM {table}
                WHERE snapshot_date = ?
                  AND year = ?
                  AND month = ?
            """
            params = (snapshot_date, target_year, target_month)
        elif definition.business_key_type == BusinessKeyType.SNAPSHOT_MONTH:
            query = f"""
                SELECT
                    COUNT(*) AS row_count,
                    MAX(snapshot_month) AS loaded_key,
                    MAX(created_at) AS created_at,
                    MAX(batch_id) AS batch_id,
                    COUNT(DISTINCT batch_id) AS distinct_batch_ids
                FROM {table}
                WHERE snapshot_month = ?
            """
            params = (sales_month,)
        else:
            query = f"""
                SELECT
                    COUNT(*) AS row_count,
                    MAX(snapshot_date) AS loaded_key,
                    MAX(created_at) AS created_at,
                    MAX(batch_id) AS batch_id,
                    COUNT(DISTINCT batch_id) AS distinct_batch_ids
                FROM {table}
                WHERE snapshot_date = ?
            """
            params = (snapshot_date,)

        with self._connection_factory.connection(self._database_type) as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            row = cursor.fetchone()
            if row is None:
                return {
                    "row_count": 0,
                    "loaded_key": None,
                    "created_at": None,
                    "batch_id": None,
                    "distinct_batch_ids": 0,
                }
            return {
                "row_count": int(row[0] or 0),
                "loaded_key": row[1].date() if hasattr(row[1], "date") else row[1],
                "created_at": row[2],
                "batch_id": int(row[3]) if row[3] is not None else None,
                "distinct_batch_ids": int(row[4] or 0),
            }

    def _latest_batch(self, batch_type: str) -> Optional[BatchRunInfo]:
        table = self._connection_factory.qualify("ctl_BatchRun", self._database_type)
        query = f"""
            SELECT TOP (1)
                batch_id, batch_type, status, started_at, finished_at, message, triggered_by
            FROM {table}
            WHERE batch_type = ?
            ORDER BY started_at DESC
        """
        with self._connection_factory.connection(self._database_type) as conn:
            cursor = conn.cursor()
            cursor.execute(query, (batch_type,))
            row = cursor.fetchone()
            if row is None:
                return None
            return BatchRunInfo(
                batch_id=int(row[0]),
                batch_type=str(row[1]),
                status=str(row[2]),
                started_at=row[3],
                finished_at=row[4],
                message=row[5],
                triggered_by=row[6],
            )

    def _classify(
        self,
        definition: PipelineDefinition,
        expected_key: date,
        summary: dict[str, Any],
        latest_batch: Optional[BatchRunInfo],
    ) -> PipelineFreshness:
        row_count = summary["row_count"]
        loaded_key = summary["loaded_key"]
        batch_id = summary["batch_id"]
        distinct_batch_ids = summary["distinct_batch_ids"]
        created_at = summary["created_at"]

        state = "ready"
        detail = "Snapshot is current and consistent."

        if latest_batch and latest_batch.status.upper() == "RUNNING":
            if batch_id is None or latest_batch.batch_id > batch_id:
                state = "refreshing"
                detail = "A newer batch is currently running."
        if state != "refreshing":
            if row_count <= 0 or loaded_key is None or batch_id is None:
                state = "missing"
                detail = "Snapshot rows or lineage are missing."
            else:
                lineage_mismatch = latest_batch is None or latest_batch.batch_id != batch_id
                latest_failed = latest_batch is not None and latest_batch.status.upper() == "FAILED"
                key_mismatch = loaded_key != expected_key
                mixed_batch_ids = distinct_batch_ids != 1
                wrong_batch_type = (
                    latest_batch is not None and latest_batch.batch_type != definition.batch_type
                )
                if any(
                    (
                        lineage_mismatch,
                        latest_failed,
                        key_mismatch,
                        mixed_batch_ids,
                        wrong_batch_type,
                    )
                ):
                    state = "partial"
                    detail = "Snapshot exists but does not match expected lineage/date."

        return PipelineFreshness(
            pipeline=definition.key,
            optional_for_optimize=definition.optional_for_optimize,
            expected_key=expected_key,
            loaded_key=loaded_key,
            row_count=row_count,
            created_at=created_at,
            batch_id=batch_id,
            latest_batch=latest_batch,
            state=state,
            detail=detail,
        )

    @staticmethod
    def _overall_state(required_states: list[str]) -> str:
        if any(item == "refreshing" for item in required_states):
            return "refreshing"
        if any(item == "missing" for item in required_states):
            return "missing"
        if any(item == "partial" for item in required_states):
            return "partial"
        return "ready"

    def _resolve_sales_snapshot_month(self, snapshot_date: date) -> date:
        dim_date = self._connection_factory.qualify_cross_db("DimDate", "source")
        query = f"""
            SELECT TOP (1) month_start.DateID AS snapshot_month
            FROM {dim_date} AS d
            INNER JOIN {dim_date} AS month_start
                ON month_start.ShamsiDay = 1
               AND (
                    CASE
                        WHEN TRY_CONVERT(INT, month_start.LongShamsiYearMonth) >= 1000000
                            THEN TRY_CONVERT(INT, month_start.LongShamsiYearMonth) / 100
                        ELSE TRY_CONVERT(INT, month_start.LongShamsiYearMonth)
                    END
                   ) = (
                    CASE
                        WHEN TRY_CONVERT(INT, d.LongShamsiYearMonth) >= 1000000
                            THEN TRY_CONVERT(INT, d.LongShamsiYearMonth) / 100
                        ELSE TRY_CONVERT(INT, d.LongShamsiYearMonth)
                    END
                   )
            WHERE d.DateID = ?
        """
        with self._connection_factory.connection("source") as conn:
            cursor = conn.cursor()
            cursor.execute(query, (snapshot_date,))
            row = cursor.fetchone()
            if row is None or row[0] is None:
                raise ValueError(
                    f"Could not resolve sales snapshot month for {snapshot_date!s}"
                )
            value = row[0]
            return value.date() if hasattr(value, "date") else value

    def _resolve_jalali_year_month(self, snapshot_date: date) -> tuple[int, int]:
        dim_date = self._connection_factory.qualify_cross_db("DimDate", "source")
        query = f"""
            SELECT TOP (1) ShamsiYear AS jalali_year, ShamsiMonth AS jalali_month
            FROM {dim_date}
            WHERE DateID = ?
        """
        with self._connection_factory.connection("source") as conn:
            cursor = conn.cursor()
            cursor.execute(query, (snapshot_date,))
            row = cursor.fetchone()
            if row is None or row[0] is None or row[1] is None:
                raise ValueError(
                    f"Could not resolve Jalali year/month for {snapshot_date!s}"
                )
            return int(row[0]), int(row[1])


__all__ = [
    "BatchRunInfo",
    "FreshnessReport",
    "PipelineFreshness",
    "SnapshotFreshnessRepository",
]
