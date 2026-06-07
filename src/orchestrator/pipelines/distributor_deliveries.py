"""Pipeline for loading historical distributor deliveries from DMS files."""

import sys
import os
import warnings
from datetime import date
from typing import Callable, List, Optional

import pandas as pd

# Suppress openpyxl warnings BEFORE importing anything that uses it
warnings.filterwarnings('ignore', category=UserWarning, module='openpyxl')
warnings.filterwarnings('ignore', message='.*Data Validation.*')
warnings.filterwarnings('ignore', message='.*Print area.*')

# Set UTF-8 encoding for Windows terminal to display Farsi characters
if sys.platform == 'win32':
    if hasattr(sys.stdout, 'reconfigure'):
        try:
            sys.stdout.reconfigure(encoding='utf-8')
        except Exception:
            pass
    if hasattr(sys.stderr, 'reconfigure'):
        try:
            sys.stderr.reconfigure(encoding='utf-8')
        except Exception:
            pass
    os.environ['PYTHONIOENCODING'] = 'utf-8'

from src.orchestrator.pipelines.pipeline_template import TemplatePipeline
from src.orchestrator.pipelines.utils import (
    load_excel_files_from_dms,
    transform_dataframe_to_staging_rows,
)
from src.orchestrator.pipelines.utils.staging_utils import (
    delete_current_year_staging_rows,
    staging_has_historical_data,
    sync_all_staging_batch_ids,
)
from src.orchestrator.services.dms import DmsClient
from src.orchestrator.services.dms.config import DmsConfigLoader


class DistributorDeliveriesPipeline(TemplatePipeline):
    """
    Pipeline for loading distributor deliveries from DMS SharePoint folders.

    Historical data (Jalali year 1404) is loaded once and retained in staging.
    Current data (Jalali year 1405) is refreshed on every run.
    """

    FILE_PATTERN = r'دیتابیس تحویل به پخش ها.*\.(xlsx|xls)$'
    HISTORICAL_YEAR = '1404'
    CURRENT_YEAR = '1405'

    EXPECTED_FILES_1404 = [
        'دیتابیس تحویل به پخش ها - اروندفارمد - 1404.xlsx',
        'دیتابیس تحویل به پخش ها - آریوژن - 1404.xlsx',
        'دیتابیس تحویل به پخش ها - اسپاد فارمد - 1404.xlsx',
        'دیتابیس تحویل به پخش ها - آلاشت - 1404.xlsx',
        'دیتابیس تحویل به پخش ها - اینوکلون - 1404.xlsx',
        'دیتابیس تحویل به پخش ها - پرسیس ژن- 1404.xlsx',
        'دیتابیس تحویل به پخش ها - سیناژن - 1404.xlsx',
        'دیتابیس تحویل به پخش ها - نانوالوند - 1404.xlsx',
        'دیتابیس تحویل به پخش ها - نوژین فارمد- 1404.xlsx',
        'دیتابیس تحویل به پخش ها - نویان پژوهان- 1404.xlsx',
        'دیتابیس تحویل به پخش ها - نیواد فارمد- 1404.xlsx',
    ]

    EXPECTED_FILES_1405 = [
        name.replace('1404', '1405') for name in EXPECTED_FILES_1404
    ]

    IGNORED_FILES = [
        f'دیتابیس تحویل به پخش ها - {HISTORICAL_YEAR}.xlsx',
        f'دیتابیس تحویل به پخش ها - {CURRENT_YEAR}.xlsx',
    ]

    PERSIAN_COLUMNS = [
        'کد دارو',
        'کالا',
        'نام پخش',
        'شماره بچ',
        'تاریخ انقضاء',
        'تعداد تحویلی',
        'تعداد تحویلی رند بالا',
        'تعداد تحویلی رند پایین',
        'تاریخ درخواست',
        'تاریخ تحویل',
        'ماه',
        'شماره نامه خروج از انبار',
        'تعداد خروج از انبار',
        'جزئیات خروج از انبار',
        'وضعیت رسید',
        'تاریخ ریلیز',
        'تعداد روز بین تاریخ تحویلی و ریلیز',
        'تعداد تحویل روتین',
        'تعداد درخواست زنجیره تامین',
        'کارخانه',
        'توضیحات',
    ]

    def __init__(
        self,
        batch_id: Optional[int],
        snapshot_date: Optional[date] = None,
        connection_factory=None,
        triggered_by: str = 'PYTHON_PIPELINE',
        database_type: str = 'test',
        historical_folder_url: Optional[str] = None,
        current_folder_url: Optional[str] = None,
        log_fn: Optional[Callable[[str], None]] = None,
    ):
        deliveries_config = DmsConfigLoader.get_distributor_deliveries_config()
        self._historical_folder_url = (
            historical_folder_url or deliveries_config['historical_folder_url']
        )
        self._current_folder_url = (
            current_folder_url or deliveries_config['current_folder_url']
        )
        self._dms_client = DmsClient()

        super().__init__(
            batch_id=batch_id,
            snapshot_date=snapshot_date,
            connection_factory=connection_factory,
            triggered_by=triggered_by,
            database_type=database_type,
            log_fn=log_fn,
            show_progress=log_fn is not None,
        )

    @property
    def batch_type(self) -> str:
        return 'DISTRIBUTOR_DELIVERIES'

    @property
    def extract_sql_path(self) -> str:
        """Not used for DMS-based pipeline, but required by TemplatePipeline."""
        return '20_etl/distributor_deliveries/extract.sql'

    @property
    def publish_procedure(self) -> str:
        return '[Data].[etl_usp_build_distributor_deliveries_snapshot]'

    @property
    def staging_table(self) -> str:
        return '[Data].[stg_DistributorDeliveries]'

    @property
    def staging_columns(self) -> List[str]:
        return [
            'batch_id',
            'drug_code',
            'product_name',
            'distributor_name',
            'batch_number',
            'expiry_date',
            'delivered_quantity',
            'delivered_quantity_round_up',
            'delivered_quantity_round_down',
            'request_date',
            'delivery_date',
            'month',
            'warehouse_exit_letter_number',
            'warehouse_exit_quantity',
            'warehouse_exit_details',
            'receipt_status',
            'release_date',
            'days_between_delivery_release',
            'routine_delivery_quantity',
            'supply_chain_request_quantity',
            'factory_name',
            'company_name',
            'description',
            'source_file',
            'row_hash',
        ]

    def transform_row_to_staging_data(self, row: tuple, columns: List[str]) -> tuple:
        raise NotImplementedError(
            "This pipeline uses DataFrame transformation, not SQL row transformation"
        )

    def load_stage(
        self,
        batch_size: int = 10000,
        incremental: bool = False,
        single_date_only: bool = False,
        force_historical_reload: bool = False,
    ) -> None:
        """
        Load data from DMS folders into staging table.

        First run (or force_historical_reload): truncate staging, load 1404 + 1405.
        Subsequent runs: delete only 1405 rows, reload 1405, keep 1404.
        """
        del incremental, single_date_only

        with self._handle_batch_failure("Load stage failed: "):
            self._ensure_snapshot_date()
            self._ensure_batch_created()

            with self._connection_factory.connection(self._database_type) as conn:
                cursor = conn.cursor()
                has_historical = staging_has_historical_data(cursor, self.staging_table)

            if force_historical_reload or not has_historical:
                self._log("Loading historical (1404) and current (1405) delivery files...")
                self._truncate_staging_table()
                df_historical = load_excel_files_from_dms(
                    dms_client=self._dms_client,
                    folder_url=self._historical_folder_url,
                    file_pattern=self.FILE_PATTERN,
                    expected_files=self.EXPECTED_FILES_1404,
                    ignored_files=self.IGNORED_FILES,
                    persian_columns=self.PERSIAN_COLUMNS,
                    log_fn=self._log_fn,
                    log_label="historical files",
                )
                df_current = load_excel_files_from_dms(
                    dms_client=self._dms_client,
                    folder_url=self._current_folder_url,
                    file_pattern=self.FILE_PATTERN,
                    expected_files=self.EXPECTED_FILES_1405,
                    ignored_files=self.IGNORED_FILES,
                    persian_columns=self.PERSIAN_COLUMNS,
                    log_fn=self._log_fn,
                    log_label="current files",
                )
                df = pd.concat([df_historical, df_current], ignore_index=True, sort=False)
            else:
                self._log("Historical (1404) data present; refreshing current (1405) files only...")
                self._delete_current_year_staging_rows()
                df = load_excel_files_from_dms(
                    dms_client=self._dms_client,
                    folder_url=self._current_folder_url,
                    file_pattern=self.FILE_PATTERN,
                    expected_files=self.EXPECTED_FILES_1405,
                    ignored_files=self.IGNORED_FILES,
                    persian_columns=self.PERSIAN_COLUMNS,
                    log_fn=self._log_fn,
                    log_label="current files",
                )

            staging_rows = transform_dataframe_to_staging_rows(
                df=df,
                batch_id=self.batch_id,
                persian_columns=self.PERSIAN_COLUMNS,
            )

            if staging_rows:
                self._load_staging_rows_in_batches(staging_rows, batch_size)

            self._sync_all_staging_batch_ids()

    def _truncate_staging_table(self) -> None:
        delete_query = f"DELETE FROM {self.staging_table}"
        with self._connection_factory.connection(self._database_type) as conn:
            cursor = conn.cursor()
            cursor.execute(delete_query)
            conn.commit()

    def _delete_current_year_staging_rows(self) -> None:
        with self._connection_factory.connection(self._database_type) as conn:
            cursor = conn.cursor()
            deleted = delete_current_year_staging_rows(cursor, self.staging_table)
            conn.commit()
            self._log(f"Removed {deleted:,} current-year (1405) staging rows before reload.")

    def _sync_all_staging_batch_ids(self) -> None:
        with self._connection_factory.connection(self._database_type) as conn:
            cursor = conn.cursor()
            updated = sync_all_staging_batch_ids(
                cursor,
                self.staging_table,
                self.batch_id,
            )
            conn.commit()
            self._log(f"Synced batch_id on {updated:,} staging rows (batch_id={self.batch_id}).")

    def _load_staging_rows_in_batches(self, staging_rows: List[tuple], batch_size: int) -> None:
        from src.orchestrator.pipelines.utils.progress_bar import RowProgressBar

        insert_query = self._get_staging_insert_query()
        total_rows = len(staging_rows)
        self._log(
            f"Inserting {total_rows:,} rows into {self.staging_table} "
            f"(batch_id={self.batch_id})..."
        )
        progress = (
            RowProgressBar(self._staging_progress_label(), total=total_rows)
            if self._show_progress
            else None
        )

        try:
            for i in range(0, total_rows, batch_size):
                if self._interrupted:
                    raise KeyboardInterrupt("Process interrupted by user")

                batch = staging_rows[i:i + batch_size]
                batch_number = (i // batch_size) + 1
                self._load_batch_to_staging(batch, insert_query, batch_number)
                loaded = min(i + len(batch), total_rows)
                if progress is not None:
                    progress.update(loaded, "inserting")
                elif batch_number == 1 or batch_number % 10 == 0:
                    self._log(f"  staged {loaded:,}/{total_rows:,} rows...")

            if progress is not None:
                progress.close("insert complete")
        except KeyboardInterrupt:
            if progress is not None:
                progress.close("failed")
            self._cleanup_partial_staging_data()
            raise
        except Exception:
            if progress is not None:
                progress.close("failed")
            raise

        self._log(
            f"Staging DB load complete: {total_rows:,} rows in "
            f"{(total_rows + batch_size - 1) // batch_size} batch(es)."
        )

    def _load_batch_to_staging(self, batch_data: List[tuple], insert_query: str, batch_number: int) -> None:
        with self._connection_factory.connection(self._database_type) as conn:
            cursor = conn.cursor()
            try:
                cursor.executemany(insert_query, batch_data)
                conn.commit()
            except Exception as e:
                conn.rollback()
                raise Exception(
                    f"Failed to load batch {batch_number} into staging: {str(e)}"
                ) from e
