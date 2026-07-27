"""Base pipeline for SQL-sourced snapshots (no staging layer)."""

from __future__ import annotations

import signal
import sys
import threading
from abc import abstractmethod
from datetime import date
from typing import Callable, Optional

from src.orchestrator.pipelines.pipeline_base import BasePipeline
from src.orchestrator.pipelines.utils import (
    has_valid_batch_id,
    INTERRUPT_MESSAGE,
    INTERRUPT_EXCEPTION_MESSAGE,
)
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
        database_type: str = "prod",
        log_fn: Optional[Callable[[str], None]] = None,
    ):
        self._batch_id = batch_id
        self._snapshot_date = snapshot_date
        self._triggered_by = triggered_by
        self._database_type = database_type
        # CLI/automate often pre-create the batch; treat that as already active.
        self._batch_created = has_valid_batch_id(batch_id)
        self._snapshot_date_detected = False
        self._interrupted = False
        self._batch_failed_marked = False
        self._log_fn = log_fn

        # Web requests may construct pipelines outside the process main thread.
        # Python only permits signal registration from the main thread.
        if threading.current_thread() is threading.main_thread():
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

    def _mark_batch_failed(self, message: str) -> None:
        """Mark the current batch FAILED in ctl_BatchRun if a valid batch_id exists."""
        batch_id = self._batch_id if has_valid_batch_id(self._batch_id) else self.batch_id
        if not has_valid_batch_id(batch_id) or self._batch_failed_marked:
            return
        try:
            self.finish_batch(batch_id, "FAILED", message)
            self._batch_failed_marked = True
        except Exception as finish_error:
            print(f"Warning: Could not mark batch as FAILED: {finish_error}")

    def _signal_handler(self, signum, frame) -> None:
        del signum, frame
        self._interrupted = True
        self._mark_batch_failed(INTERRUPT_MESSAGE)
        raise KeyboardInterrupt(INTERRUPT_EXCEPTION_MESSAGE)

    def _finish_success_if_standalone(self, message: str = "OK") -> None:
        """Mark batch SUCCESS when load/publish is called outside run()."""
        if self._in_run_method:
            return
        if has_valid_batch_id(self.batch_id):
            self.finish_batch(self.batch_id, "SUCCESS", message)

    def load_stage(self, **kwargs) -> None:
        """No-op: snapshot procedures read source tables directly."""
        del kwargs
        with self._handle_batch_failure("Prepare batch failed: "):
            self._ensure_snapshot_date()
            self._ensure_batch_created()
            self._log(f"Batch {self.batch_id} ready for snapshot publish.")
        self._finish_success_if_standalone("Batch prepared")

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
        self._finish_success_if_standalone("Snapshot publish complete")

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
            self._mark_batch_failed(INTERRUPT_MESSAGE)
            raise
