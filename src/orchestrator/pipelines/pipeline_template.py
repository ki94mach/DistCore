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
from src.orchestrator.pipelines.utils.extract_cache import (
    ExtractCache,
    ExtractCacheError,
    compute_extract_query_hash,
    get_default_cache_root,
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
        cache_dir: Optional[Path] = None,
    ):
        self._batch_id = batch_id
        self._snapshot_date = snapshot_date
        self._triggered_by = triggered_by
        self._database_type = database_type
        self._batch_created = False
        self._snapshot_date_detected = False
        self._interrupted = False
        self._cache_dir = cache_dir or get_default_cache_root(Path(__file__))

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

    def _get_extract_cache(self) -> ExtractCache:
        return ExtractCache(self._cache_dir, self.batch_type, self.batch_id)

    def _compute_query_hash(
        self,
        extract_query: str,
        since_date: Optional[date],
        single_date_only: bool,
    ) -> str:
        return compute_extract_query_hash(
            extract_query=extract_query,
            batch_type=self.batch_type,
            since_date=since_date,
            snapshot_date=self.snapshot_date,
            single_date_only=single_date_only,
        )

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
        use_cache: bool = True,
        force_extract: bool = False,
        extract_only: bool = False,
        load_from_cache_only: bool = False,
    ) -> None:
        with self._handle_batch_failure("Load stage failed: "):
            self._ensure_snapshot_date()
            self._ensure_batch_created()

            since_date, use_equality_filter = self._determine_date_filter(
                incremental, single_date_only
            )

            extract_query = self._build_extract_query(since_date, use_equality_filter)
            self._run_staged_load(
                extract_query=extract_query,
                batch_size=batch_size,
                since_date=since_date,
                single_date_only=single_date_only,
                use_cache=use_cache,
                force_extract=force_extract,
                extract_only=extract_only,
                load_from_cache_only=load_from_cache_only,
            )

    def _run_staged_load(
        self,
        extract_query: str,
        batch_size: int,
        since_date: Optional[date],
        single_date_only: bool,
        use_cache: bool = True,
        force_extract: bool = False,
        extract_only: bool = False,
        load_from_cache_only: bool = False,
    ) -> None:
        query_hash = self._compute_query_hash(extract_query, since_date, single_date_only)

        if load_from_cache_only and extract_only:
            raise ValueError("extract_only and load_from_cache_only cannot both be True.")

        if not use_cache:
            self._prepare_staging_table()
            try:
                self._extract_and_load_batches_inline(extract_query, batch_size)
            except KeyboardInterrupt:
                self._cleanup_partial_staging_data()
                raise
            return

        cache = self._get_extract_cache()

        if load_from_cache_only:
            try:
                cache.require_extract_complete(query_hash)
            except ExtractCacheError as exc:
                raise ExtractCacheError(str(exc)) from exc
        else:
            need_extract = force_extract or not cache.is_extract_complete(query_hash)
            if need_extract:
                try:
                    self._extract_to_cache(
                        extract_query=extract_query,
                        batch_size=batch_size,
                        query_hash=query_hash,
                        force_extract=force_extract,
                    )
                except KeyboardInterrupt:
                    cache.clear()
                    raise
            elif extract_only:
                return

        if extract_only:
            return

        self._prepare_staging_table()
        try:
            self._load_cache_to_staging(batch_size=batch_size, query_hash=query_hash)
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

    def _extract_to_cache(
        self,
        extract_query: str,
        batch_size: int,
        query_hash: str,
        force_extract: bool,
    ) -> None:
        cache = self._get_extract_cache()
        if force_extract:
            cache.clear()

        cache.begin_extract(query_hash)
        chunk_files: List[str] = []
        row_count = 0
        column_names: List[str] = []
        chunk_index = 0

        try:
            with self._connection_factory.connection('source') as source_conn:
                source_cursor = source_conn.cursor()
                source_cursor.arraysize = batch_size
                source_cursor.execute(extract_query)
                column_names = [column[0] for column in source_cursor.description]

                while True:
                    if self._interrupted:
                        raise KeyboardInterrupt("Process interrupted by user")

                    rows = source_cursor.fetchmany(batch_size)
                    if not rows:
                        break

                    chunk_index += 1
                    chunk_files.append(
                        cache.write_chunk(chunk_index, list(rows), column_names)
                    )
                    row_count += len(rows)

            cache.finalize_extract(
                query_hash=query_hash,
                chunk_files=chunk_files,
                row_count=row_count,
                column_names=column_names,
            )
        except Exception:
            cache.clear()
            raise

    def _load_cache_to_staging(self, batch_size: int, query_hash: str) -> None:
        cache = self._get_extract_cache()
        insert_query = self._get_staging_insert_query()
        batch_number = 0

        for columns, rows in cache.iter_chunks(query_hash):
            for offset in range(0, len(rows), batch_size):
                if self._interrupted:
                    raise KeyboardInterrupt("Process interrupted by user")

                chunk_rows = rows[offset:offset + batch_size]
                batch_data = [
                    self.transform_row_to_staging_data(row, columns)
                    for row in chunk_rows
                ]
                batch_number += 1
                self._load_batch_to_staging(batch_data, insert_query, batch_number)

        cache.delete_cache()

    def _extract_and_load_batches_inline(self, extract_query: str, batch_size: int) -> None:
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
