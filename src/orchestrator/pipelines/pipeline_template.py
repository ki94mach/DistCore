import signal
import sys
from abc import abstractmethod
from datetime import date, timedelta
from pathlib import Path
from typing import List, Optional, Tuple

from src.orchestrator.pipelines.pipeline_base import BasePipeline
from src.orchestrator.pipelines.utils import (
    apply_date_equality_filter,
    get_sql_folder_path,
    parse_select_statement,
    substitute_date_parameter,
)
from src.orchestrator.services.sql_server_db.executors.sql_utils import (
    read_sql_file,
    resolve_sql_file_path,
)


class TemplatePipeline(BasePipeline):
    """
    Template-method base for inventory pipelines with shared staging logic.
    """

    def __init__(
        self,
        batch_id: Optional[int],
        snapshot_date: Optional[date] = None,
        connection_factory=None,
        triggered_by: str = 'PYTHON_PIPELINE',
        database_type: str = 'test',
    ):
        self._batch_id = batch_id
        self._snapshot_date = snapshot_date
        self._triggered_by = triggered_by
        self._database_type = database_type
        self._batch_created = False
        self._snapshot_date_detected = False
        self._interrupted = False

        signal.signal(signal.SIGINT, self._signal_handler)
        if sys.platform != 'win32':
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
    def extract_sql_path(self) -> str:
        raise NotImplementedError

    @property
    @abstractmethod
    def publish_procedure(self) -> str:
        raise NotImplementedError

    @property
    @abstractmethod
    def staging_table(self) -> str:
        raise NotImplementedError

    @property
    @abstractmethod
    def staging_columns(self) -> List[str]:
        raise NotImplementedError

    @property
    def staging_date_column(self) -> str:
        return "as_of_datetime"

    @abstractmethod
    def transform_row_to_staging_data(self, row: tuple, columns: List[str]) -> tuple:
        raise NotImplementedError

    def _ensure_snapshot_date(self) -> None:
        if self._snapshot_date_detected:
            return

        if self._snapshot_date is None:
            today = date.today()
            self._snapshot_date = today
            object.__setattr__(self, 'snapshot_date', today)
        self._snapshot_date_detected = True

    def _ensure_batch_created(self) -> None:
        if self._batch_created:
            return

        if (self._batch_id is None or self._batch_id == 0) or (
            hasattr(self, 'batch_id') and self.batch_id == 0
        ):
            result = self.execute_procedure_with_output(
                '[Data].[ctl_usp_start_batch]',
                parameters={
                    'batch_type': self.batch_type,
                    'triggered_by': self._triggered_by,
                },
                output_parameters=['batch_id'],
                database_type=self._database_type,
            )

            self._batch_id = result['batch_id']
            object.__setattr__(self, 'batch_id', self._batch_id)
            self._batch_created = True

    def _signal_handler(self, signum, frame) -> None:
        self._interrupted = True
        if self._batch_created and self._batch_id:
            try:
                self.finish_batch(self._batch_id, 'FAILED', 'Process interrupted by user (Ctrl+C)')
            except Exception:
                pass
        raise KeyboardInterrupt("Process interrupted by user")

    def load_stage(
        self,
        batch_size: int = 10000,
        incremental: bool = True,
        single_date_only: bool = False,
    ) -> None:
        with self._handle_batch_failure("Load stage failed: "):
            self._ensure_snapshot_date()
            self._ensure_batch_created()

            since_date, use_equality_filter = self._determine_date_filter(
                incremental, single_date_only
            )

            extract_query = self._build_extract_query(since_date, use_equality_filter)
            self._prepare_staging_table()

            try:
                self._extract_and_load_batches(extract_query, batch_size)
            except KeyboardInterrupt:
                self._cleanup_partial_staging_data()
                raise

    def _determine_date_filter(
        self, incremental: bool, single_date_only: bool
    ) -> Tuple[Optional[date], bool]:
        if single_date_only:
            return self.snapshot_date, True

        if incremental:
            latest_date = self._get_latest_staging_date()
            if latest_date:
                return latest_date + timedelta(days=1), False

        return None, False

    def _get_latest_staging_date(self) -> Optional[date]:
        with self._connection_factory.connection('test') as test_conn:
            test_cursor = test_conn.cursor()
            test_cursor.execute(
                f"""
                SELECT MAX({self.staging_date_column}) AS latest_date
                FROM {self.staging_table}
                """
            )
            result = test_cursor.fetchone()
            return result[0] if result and result[0] is not None else None

    def _build_extract_query(self, since_date: Optional[date], use_equality_filter: bool) -> str:
        sql_folder = get_sql_folder_path(Path(__file__))
        sql_path = resolve_sql_file_path(self.extract_sql_path, sql_folder)
        query_template = read_sql_file(sql_path)

        select_statement = parse_select_statement(query_template)
        query = substitute_date_parameter(select_statement, 'since', since_date)

        if use_equality_filter and since_date:
            query = apply_date_equality_filter(query, '[FKDate]', since_date)

        return query

    def _prepare_staging_table(self) -> None:
        delete_query = f"DELETE FROM {self.staging_table} WHERE batch_id = ?"

        with self._connection_factory.connection('test') as test_conn:
            test_cursor = test_conn.cursor()
            test_cursor.execute(delete_query, (self.batch_id,))
            test_conn.commit()

    def _get_staging_insert_query(self) -> str:
        columns = ", ".join(self.staging_columns)
        placeholders = ", ".join(["?"] * len(self.staging_columns))
        return f"""
            INSERT INTO {self.staging_table}
                ({columns})
            VALUES ({placeholders})
        """

    def _load_batch_to_staging(self, batch_data: List[tuple], insert_query: str, batch_number: int) -> None:
        with self._connection_factory.connection('test') as test_conn:
            test_cursor = test_conn.cursor()
            try:
                test_cursor.executemany(insert_query, batch_data)
                test_conn.commit()
            except Exception as e:
                test_conn.rollback()
                raise Exception(
                    f"Failed to load batch {batch_number} into staging: {str(e)}"
                ) from e

    def _extract_and_load_batches(self, extract_query: str, batch_size: int) -> None:
        insert_query = self._get_staging_insert_query()
        batch_count = 0

        with self._connection_factory.connection('source') as source_conn:
            source_cursor = source_conn.cursor()
            source_cursor.arraysize = batch_size
            source_cursor.execute(extract_query)

            columns = [column[0] for column in source_cursor.description]

            while True:
                if self._interrupted:
                    raise KeyboardInterrupt("Process interrupted by user")

                rows = source_cursor.fetchmany(batch_size)
                if not rows:
                    break

                batch_data = [
                    self.transform_row_to_staging_data(row, columns)
                    for row in rows
                ]

                batch_count += 1
                self._load_batch_to_staging(batch_data, insert_query, batch_count)

    def _cleanup_partial_staging_data(self) -> None:
        delete_query = f"DELETE FROM {self.staging_table} WHERE batch_id = ?"

        try:
            with self._connection_factory.connection('test') as test_conn:
                test_cursor = test_conn.cursor()
                test_cursor.execute(delete_query, (self.batch_id,))
                test_conn.commit()
        except Exception:
            pass

    def publish(self) -> None:
        with self._handle_batch_failure("Publish failed: "):
            self._ensure_snapshot_date()
            self._ensure_batch_created()
            self.execute_procedure(
                self.publish_procedure,
                parameters={
                    'batch_id': self.batch_id,
                    'snapshot_date': self.snapshot_date,
                },
                database_type=self._database_type,
            )

    def finish_batch(self, batch_id: int, status: str, message: str = '') -> None:
        fresh_conn = self._connection_factory.get_connection(
            self._database_type,
            use_pool=False,
        )
        try:
            fresh_conn.autocommit = True

            cursor = fresh_conn.cursor()
            exec_sql = "EXEC [Data].[ctl_usp_finish_batch] @batch_id = ?, @status = ?, @message = ?"
            param_values = [batch_id, status, message]

            cursor.execute(exec_sql, param_values)
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
                    self.finish_batch(self._batch_id, 'FAILED', 'Process interrupted by user (Ctrl+C)')
                except Exception:
                    pass
            raise
