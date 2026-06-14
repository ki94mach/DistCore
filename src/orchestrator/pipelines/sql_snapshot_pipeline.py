"""Base pipeline for SQL-sourced snapshots (no staging layer)."""

from __future__ import annotations

import signal
import sys
from abc import abstractmethod
from datetime import date
from typing import Callable, Optional

from src.orchestrator.pipelines.pipeline_base import BasePipeline
from src.orchestrator.pipelines.utils import has_valid_batch_id
from src.orchestrator.services.sql_server_db.factory import DBConnectionFactory


class SqlSnapshotPipeline(BasePipeline):
    """
    Pipeline that publishes snapshots via stored procedures reading DWOrchid directly.

    Flow: start batch -> publish snapshot proc -> finish batch.
    """

    def __init__(
        self,
        batch_id: Optional[int],
        snapshot_date: Optional[date] = None,
        connection_factory: Optional[DBConnectionFactory] = None,
        triggered_by: str = "PYTHON_PIPELINE",
        database_type: str = "test",
        log_fn: Optional[Callable[[str], None]] = None,
    ):
        self._batch_id = batch_id
        self._snapshot_date = snapshot_date
        self._triggered_by = triggered_by
        self._database_type = database_type
        self._batch_created = False
        self._snapshot_date_detected = False
        self._interrupted = False
        self._log_fn = log_fn

        signal.signal(signal.SIGINT, self._signal_handler)
        if sys.platform != "win32":
            signal.signal(signal.SIGTERM, self._signal_handler)

        placeholder_date = snapshot_date if snapshot_date is not None else date.today()
        super().__init__(
            batch_id=batch_id if batch_id is not None else 0,
            snapshot_date=placeholder_date,
            connection_factory=connection_factory,
        )

    @property
    @abstractmethod
    def batch_type(self) -> str:
        raise NotImplementedError

    @property
    @abstractmethod
    def publish_procedure(self) -> str:
        raise NotImplementedError

    def _log(self, message: str) -> None:
        if self._log_fn is not None:
            self._log_fn(message)

    def _qualify(self, object_name: str, database_type: Optional[str] = None) -> str:
        db_type = database_type or self._database_type
        return self._connection_factory.qualify(object_name, db_type)

    def _ensure_snapshot_date(self) -> None:
        if self._snapshot_date_detected:
            return
        if self._snapshot_date is None:
            today = date.today()
            self._snapshot_date = today
            object.__setattr__(self, "snapshot_date", today)
        self._snapshot_date_detected = True

    def _ensure_batch_created(self) -> None:
        if self._batch_created:
            return
        if self._batch_id is None or self._batch_id == 0 or self.batch_id == 0:
            result = self.execute_procedure_with_output(
                self._qualify("ctl_usp_start_batch"),
                parameters={
                    "batch_type": self.batch_type,
                    "triggered_by": self._triggered_by,
                },
                output_parameters=["batch_id"],
                database_type=self._database_type,
            )
            self._batch_id = result["batch_id"]
            object.__setattr__(self, "batch_id", self._batch_id)
        self._batch_created = True

    def _signal_handler(self, signum, frame) -> None:
        del signum, frame
        self._interrupted = True
        if self._batch_created and self._batch_id:
            try:
                self.finish_batch(self._batch_id, "FAILED", "Process interrupted by user (Ctrl+C)")
            except Exception:
                pass
        raise KeyboardInterrupt("Process interrupted by user")

    def load_stage(self, **kwargs) -> None:
        """No-op: snapshot procedures read source tables directly."""
        del kwargs
        with self._handle_batch_failure("Prepare batch failed: "):
            self._ensure_snapshot_date()
            self._ensure_batch_created()
            self._log(f"Batch {self.batch_id} ready for snapshot publish.")

    def publish(self) -> None:
        with self._handle_batch_failure("Publish failed: "):
            self._ensure_snapshot_date()
            self._ensure_batch_created()
            self._log(
                f"Publishing {self.batch_type} snapshot "
                f"(batch_id={self.batch_id}, snapshot_date={self.snapshot_date})..."
            )
            self.execute_procedure(
                self.publish_procedure,
                parameters={
                    "batch_id": self.batch_id,
                    "snapshot_date": self.snapshot_date,
                },
                database_type=self._database_type,
            )
            self._log("Snapshot publish complete.")

    def finish_batch(self, batch_id: int, status: str, message: str = "") -> None:
        fresh_conn = self._connection_factory.get_connection(
            self._database_type,
            use_pool=False,
        )
        try:
            fresh_conn.autocommit = True
            cursor = fresh_conn.cursor()
            cursor.execute(
                f"EXEC {self._qualify('ctl_usp_finish_batch')} @batch_id = ?, @status = ?, @message = ?",
                [batch_id, status, message],
            )
        finally:
            fresh_conn.close()

    def run(self) -> None:
        self._ensure_snapshot_date()
        self._ensure_batch_created()
        try:
            super().run()
        except KeyboardInterrupt:
            if self._batch_created and self._batch_id:
                try:
                    self.finish_batch(self._batch_id, "FAILED", "Process interrupted by user (Ctrl+C)")
                except Exception:
                    pass
            raise
