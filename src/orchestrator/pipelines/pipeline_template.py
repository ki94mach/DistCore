import signal
import sys
from abc import abstractmethod
from datetime import date, timedelta
from pathlib import Path
from typing import Callable, List, Optional, Tuple

import pandas as pd

from src.orchestrator.pipelines.pipeline_base import BasePipeline
from src.orchestrator.pipelines.utils import (
    apply_date_equality_filter,
    get_sql_folder_path,
    parse_select_statement,
    substitute_date_parameter,
)
from src.orchestrator.pipelines.utils.progress_bar import RowProgressBar
from src.orchestrator.pipelines.utils.extract_cache import (
    VERIFIED_SOURCE_CACHE,
    VERIFIED_STAGING,
    ExtractCache,
    ExtractCacheError,
    compute_extract_query_hash,
    get_default_cache_root,
)
from src.orchestrator.pipelines.utils.batch_reconciliation import (
    reconcile_before_publish,
    reconcile_before_staging_load,
)
from src.orchestrator.pipelines.utils.stage_verification import (
    StageVerificationError,
    count_source_rows,
    count_staging_rows,
    verify_cache_staging_match,
    verify_source_cache_match,
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
        log_fn: Optional[Callable[[str], None]] = None,
        show_progress: bool = False,
    ):
        self._batch_id = batch_id
        self._snapshot_date = snapshot_date
        self._triggered_by = triggered_by
        self._database_type = database_type
        self._batch_created = False
        self._snapshot_date_detected = False
        self._interrupted = False
        self._cache_dir = cache_dir or get_default_cache_root(Path(__file__))
        self._log_fn = log_fn
        self._show_progress = show_progress

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
    def snapshot_table(self) -> Optional[str]:
        """Snapshot table for batch-scoped publish cleanup; None if not applicable."""
        return None

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

    def _log(self, message: str) -> None:
        if self._log_fn is not None:
            self._log_fn(message)

    def _staging_progress_label(self, suffix: str = "") -> str:
        table = self.staging_table
        if "." in table:
            short = table.rsplit(".", 1)[-1].strip("[]")
        else:
            short = table
        label = f"Load staging DB ({short})"
        return f"{label} {suffix}".strip() if suffix else label

    def _load_staging_from_rows(
        self,
        rows: List[tuple],
        columns: List[str],
        batch_size: int,
        *,
        progress_label: Optional[str] = None,
    ) -> int:
        """Insert transformed rows into the staging table with optional progress bar."""
        insert_query = self._get_staging_insert_query()
        total_rows = len(rows)
        label = progress_label or self._staging_progress_label()
        self._log(
            f"Inserting {total_rows:,} rows into {self.staging_table} "
            f"(batch_id={self.batch_id}, batch_size={batch_size:,})..."
        )
        progress = (
            RowProgressBar(label, total=total_rows)
            if self._show_progress
            else None
        )
        batch_number = 0

        try:
            for offset in range(0, total_rows, batch_size):
                if self._interrupted:
                    raise KeyboardInterrupt("Process interrupted by user")

                chunk_rows = rows[offset:offset + batch_size]
                batch_data = [
                    self.transform_row_to_staging_data(row, columns)
                    for row in chunk_rows
                ]
                batch_number += 1
                self._load_batch_to_staging(batch_data, insert_query, batch_number)
                loaded = min(offset + len(chunk_rows), total_rows)
                if progress is not None:
                    progress.update(loaded, "inserting")
                elif batch_number == 1 or batch_number % 10 == 0:
                    self._log(f"  staged {loaded:,}/{total_rows:,} rows...")

            if progress is not None:
                progress.close("insert complete")
        except Exception:
            if progress is not None:
                progress.close("failed")
            raise

        self._log(
            f"Staging DB load complete: {total_rows:,} rows in {batch_number} batch(es)."
        )
        return batch_number

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
        max_verification_retries: int = 3,
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
                max_verification_retries=max_verification_retries,
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
        max_verification_retries: int = 3,
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
        cache_query_hash = self._cache_query_hash_for_load(
            cache, query_hash, load_from_cache_only=load_from_cache_only
        )

        if load_from_cache_only:
            reconcile_before_staging_load(
                connection_factory=self._connection_factory,
                batch_id=self.batch_id,
                batch_type=self.batch_type,
                staging_table=self.staging_table,
                snapshot_table=self.snapshot_table,
                cache=cache,
                query_hash=cache_query_hash,
                log_fn=self._log,
                database_type=self._database_type,
            )
            cache.require_source_cache_verified(cache_query_hash)
        else:
            self._run_extract_with_verification(
                extract_query=extract_query,
                batch_size=batch_size,
                query_hash=query_hash,
                force_extract=force_extract,
                max_verification_retries=max_verification_retries,
            )
            if extract_only:
                return

        self._run_load_with_verification(
            extract_query=extract_query,
            batch_size=batch_size,
            query_hash=cache_query_hash,
            max_verification_retries=max_verification_retries,
        )

    def _cache_query_hash_for_load(
        self,
        cache: ExtractCache,
        run_query_hash: str,
        *,
        load_from_cache_only: bool,
    ) -> str:
        """Hash used for cache I/O; load-from-cache always uses the manifest hash."""
        manifest = cache.read_manifest()
        if not manifest or not manifest.get("extract_query_hash"):
            raise ExtractCacheError(
                f"No extract cache found for {self.batch_type} batch {self.batch_id}. "
                "Run extract to cache first."
            )
        cache_hash = str(manifest["extract_query_hash"])
        if load_from_cache_only and cache_hash != run_query_hash:
            self._log(
                "Load-from-cache: using extract parameters stored in cache "
                "(CLI snapshot/load options may differ from when extract ran)."
            )
        return cache_hash if load_from_cache_only else run_query_hash

    def _run_extract_with_verification(
        self,
        extract_query: str,
        batch_size: int,
        query_hash: str,
        force_extract: bool,
        max_verification_retries: int,
    ) -> None:
        cache = self._get_extract_cache()
        last_error: Optional[Exception] = None

        for attempt in range(1, max_verification_retries + 1):
            try:
                if force_extract or not cache.is_source_cache_verified(query_hash):
                    if force_extract:
                        self._log("Clearing cache (force re-extract).")
                        cache.clear()
                    self._log(
                        f"Extract attempt {attempt}/{max_verification_retries}: "
                        "querying source database..."
                    )
                    try:
                        self._extract_to_cache(
                            extract_query=extract_query,
                            batch_size=batch_size,
                            query_hash=query_hash,
                        )
                    except KeyboardInterrupt:
                        cache.clear()
                        raise
                else:
                    self._log(
                        f"Extract attempt {attempt}/{max_verification_retries}: "
                        "using existing verified cache."
                    )

                self._log("Verifying source row count vs cache...")
                source_count = count_source_rows(self._connection_factory, extract_query)
                cache_count = cache.get_manifest_row_count(query_hash)
                verify_source_cache_match(
                    source_count=source_count,
                    cache_count=cache_count,
                    step_label="Source vs cache",
                )
                cache.set_verified_step(
                    VERIFIED_SOURCE_CACHE,
                    source_row_count=source_count,
                )
                self._log(
                    f"Source/cache verified: {source_count:,} rows "
                    f"(step={VERIFIED_SOURCE_CACHE})."
                )
                return
            except (StageVerificationError, ExtractCacheError) as exc:
                last_error = exc
                self._log(f"Source/cache verification failed: {exc}")
                cache.clear()

        raise StageVerificationError(
            f"Source/cache verification failed after {max_verification_retries} attempts: "
            f"{last_error}"
        ) from last_error

    def _run_load_with_verification(
        self,
        extract_query: str,
        batch_size: int,
        query_hash: str,
        max_verification_retries: int,
    ) -> None:
        cache = self._get_extract_cache()
        last_error: Optional[Exception] = None

        if not cache.is_source_cache_verified(query_hash):
            self._log("Cache not source-verified; running extract first.")
            self._run_extract_with_verification(
                extract_query=extract_query,
                batch_size=batch_size,
                query_hash=query_hash,
                force_extract=False,
                max_verification_retries=max_verification_retries,
            )

        reconcile_before_staging_load(
            connection_factory=self._connection_factory,
            batch_id=self.batch_id,
            batch_type=self.batch_type,
            staging_table=self.staging_table,
            snapshot_table=self.snapshot_table,
            cache=cache,
            query_hash=query_hash,
            log_fn=self._log,
            database_type=self._database_type,
        )

        for attempt in range(1, max_verification_retries + 1):
            try:
                self._log(
                    f"Load attempt {attempt}/{max_verification_retries}: "
                    f"preparing staging table {self.staging_table}..."
                )
                self._prepare_staging_table()
                try:
                    self._load_rows_from_cache(batch_size=batch_size, query_hash=query_hash)
                except KeyboardInterrupt:
                    self._cleanup_partial_staging_data()
                    raise

                cache_count = cache.get_manifest_row_count(query_hash)
                self._log(
                    f"Verifying cache vs staging DB ({self.staging_table}, "
                    f"batch_id={self.batch_id})..."
                )
                verify_progress = (
                    RowProgressBar(
                        self._staging_progress_label("verify"),
                        total=cache_count,
                    )
                    if self._show_progress
                    else None
                )
                if verify_progress is not None:
                    verify_progress.update(0, "counting")
                staging_count = count_staging_rows(
                    self._connection_factory,
                    self.staging_table,
                    self.batch_id,
                )
                if verify_progress is not None:
                    verify_progress.update(
                        staging_count,
                        "ok" if staging_count == cache_count else "mismatch",
                    )
                    verify_progress.close()
                verify_cache_staging_match(
                    cache_count=cache_count,
                    staging_count=staging_count,
                    step_label="Cache vs staging",
                )
                cache.set_verified_step(VERIFIED_STAGING)
                self._log(
                    f"Cache/staging verified: {cache_count:,} rows loaded to staging "
                    f"(batch_id={self.batch_id})."
                )
                cache.delete_cache()
                self._log("Extract cache deleted after successful load.")
                return
            except (StageVerificationError, ExtractCacheError) as exc:
                last_error = exc
                self._log(f"Cache/staging verification failed: {exc}")
                self._cleanup_partial_staging_data()
                if not cache.is_source_cache_verified(query_hash):
                    self._log("Re-running extract after staging mismatch.")
                    self._run_extract_with_verification(
                        extract_query=extract_query,
                        batch_size=batch_size,
                        query_hash=query_hash,
                        force_extract=True,
                        max_verification_retries=max_verification_retries,
                    )

        raise StageVerificationError(
            f"Cache/staging verification failed after {max_verification_retries} attempts: "
            f"{last_error}"
        ) from last_error

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
    ) -> None:
        cache = self._get_extract_cache()
        cache.begin_extract(query_hash)
        all_rows: List[tuple] = []
        column_names: List[str] = []
        progress = RowProgressBar("Extract from source") if self._show_progress else None

        try:
            with self._connection_factory.connection('source') as source_conn:
                source_cursor = source_conn.cursor()
                source_cursor.arraysize = batch_size
                source_cursor.execute(extract_query)
                column_names = [column[0] for column in source_cursor.description]
                self._log(
                    f"Reading from source ({len(column_names)} columns: "
                    f"{', '.join(column_names)})..."
                )

                while True:
                    if self._interrupted:
                        raise KeyboardInterrupt("Process interrupted by user")

                    rows = source_cursor.fetchmany(batch_size)
                    if not rows:
                        break
                    # Plain tuples: pyodbc.Row is not expanded correctly by pandas DataFrame.
                    all_rows.extend(tuple(row) for row in rows)
                    if progress is not None:
                        progress.update(len(all_rows), "fetching")
                    elif len(all_rows) <= batch_size or len(all_rows) % (batch_size * 10) < batch_size:
                        self._log(f"  fetched {len(all_rows):,} rows from source...")

            if progress is not None:
                progress.close("fetch complete")

            self._log(f"Writing {len(all_rows):,} rows to extract cache...")
            df = pd.DataFrame(all_rows, columns=column_names)
            cache.write_extract(df, query_hash)
            self._log(f"Cache written: {cache.extract_path}")
        except Exception:
            if progress is not None:
                progress.close("failed")
            cache.clear()
            raise

    def _load_rows_from_cache(self, batch_size: int, query_hash: str) -> None:
        cache = self._get_extract_cache()
        df = cache.read_extract(query_hash)
        columns = [str(col) for col in df.columns]
        rows = [tuple(record) for record in df.itertuples(index=False, name=None)]
        self._log(f"Loading {len(rows):,} rows from cache into staging database...")
        self._load_staging_from_rows(
            rows,
            columns,
            batch_size,
            progress_label=self._staging_progress_label("from cache"),
        )

    def _extract_and_load_batches_inline(self, extract_query: str, batch_size: int) -> None:
        insert_query = self._get_staging_insert_query()
        batch_count = 0
        rows_loaded = 0
        columns: List[str] = []
        progress = (
            RowProgressBar(
                self._staging_progress_label("from source"),
                total=None,
            )
            if self._show_progress
            else None
        )

        self._log(
            f"Streaming from source into staging DB {self.staging_table} "
            f"(batch_id={self.batch_id})..."
        )

        try:
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
                        self.transform_row_to_staging_data(tuple(row), columns)
                        for row in rows
                    ]

                    batch_count += 1
                    self._load_batch_to_staging(batch_data, insert_query, batch_count)
                    rows_loaded += len(rows)
                    if progress is not None:
                        progress.update(rows_loaded, "inserting")
                    elif batch_count == 1 or batch_count % 10 == 0:
                        self._log(f"  staged {rows_loaded:,} rows...")

            if progress is not None:
                progress.close("insert complete")
        except Exception:
            if progress is not None:
                progress.close("failed")
            raise

        self._log(
            f"Staging DB load complete: {rows_loaded:,} rows in {batch_count} batch(es)."
        )

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

            cache = self._get_extract_cache()
            manifest = cache.read_manifest()
            query_hash = manifest.get("extract_query_hash") if manifest else None
            reconcile_before_publish(
                connection_factory=self._connection_factory,
                batch_id=self.batch_id,
                batch_type=self.batch_type,
                staging_table=self.staging_table,
                snapshot_table=self.snapshot_table,
                cache=cache if cache.exists else None,
                query_hash=query_hash,
                log_fn=self._log,
                database_type=self._database_type,
            )

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
