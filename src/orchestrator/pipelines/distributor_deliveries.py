"""Pipeline for loading distributor deliveries from DMS into fact table and publishing snapshot."""

import os
import sys
import warnings
from datetime import date
from typing import Callable, List, Optional

warnings.filterwarnings("ignore", category=UserWarning, module="openpyxl")
warnings.filterwarnings("ignore", message=".*Data Validation.*")
warnings.filterwarnings("ignore", message=".*Print area.*")

if sys.platform == "win32":
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8")
            except Exception:
                pass
    os.environ["PYTHONIOENCODING"] = "utf-8"

from src.orchestrator.pipelines.sql_snapshot_pipeline import SqlSnapshotPipeline
from src.orchestrator.pipelines.utils.delivery_fact_utils import (
    count_fact_rows,
    delete_current_year_fact_rows,
    historical_and_current_years,
    source_file_pattern_for_year,
)
from src.orchestrator.pipelines.utils.delivery_file_utils import (
    concat_delivery_dataframes,
    load_excel_files_from_dms,
    transform_dataframe_to_fact_rows,
)
from src.orchestrator.pipelines.utils.progress_bar import RowProgressBar
from src.orchestrator.services.dms import DmsClient
from src.orchestrator.services.dms.config import DmsConfigLoader


_FACTORY_BASE_NAMES = [
    "اروندفارمد",
    "آریوژن",
    "اسپاد فارمد",
    "آلاشت",
    "اینوکلون",
    "پرسیس ژن",
    "سیناژن",
    "نانوالوند",
    "نوژین فارمد",
    "نویان پژوهان",
    "نیواد فارمد",
]


def _expected_files_for_year(year: str) -> List[str]:
    files = []
    for name in _FACTORY_BASE_NAMES:
        # Preserve known hyphen quirks from the original expected list.
        if name in ("پرسیس ژن", "نوژین فارمد", "نویان پژوهان", "نیواد فارمد"):
            files.append(f"دیتابیس تحویل به پخش ها - {name}- {year}.xlsx")
        else:
            files.append(f"دیتابیس تحویل به پخش ها - {name} - {year}.xlsx")
    return files


class DistributorDeliveriesPipeline(SqlSnapshotPipeline):
    """
    Load delivery Excel files from DMS into [Data].[fact_DistributorDeliveries], then publish snapshot.

    Historical (previous Jalali year) data is loaded once and retained.
    Current Jalali year data is refreshed each run.
    """

    FILE_PATTERN = r"دیتابیس تحویل به پخش ها.*\.(xlsx|xls)$"

    PERSIAN_COLUMNS = [
        "کد دارو",
        "کالا",
        "نام پخش",
        "شماره بچ",
        "تاریخ انقضاء",
        "تعداد تحویلی",
        "تعداد تحویلی رند بالا",
        "تعداد تحویلی رند پایین",
        "تاریخ درخواست",
        "تاریخ تحویل",
        "ماه",
        "شماره نامه خروج از انبار",
        "تعداد خروج از انبار",
        "جزئیات خروج از انبار",
        "وضعیت رسید",
        "تاریخ ریلیز",
        "تعداد روز بین تاریخ تحویلی و ریلیز",
        "تعداد تحویل روتین",
        "تعداد درخواست زنجیره تامین",
        "کارخانه",
        "توضیحات",
    ]

    FACT_COLUMNS = [
        "drug_code",
        "product_name",
        "distributor_name",
        "batch_number",
        "expiry_date",
        "delivered_quantity",
        "delivered_quantity_round_up",
        "delivered_quantity_round_down",
        "request_date",
        "delivery_date",
        "month",
        "warehouse_exit_letter_number",
        "warehouse_exit_quantity",
        "warehouse_exit_details",
        "receipt_status",
        "release_date",
        "days_between_delivery_release",
        "routine_delivery_quantity",
        "supply_chain_request_quantity",
        "factory_name",
        "company_name",
        "description",
        "source_file",
        "row_hash",
    ]

    def __init__(
        self,
        batch_id: Optional[int],
        snapshot_date: Optional[date] = None,
        connection_factory=None,
        triggered_by: str = "PYTHON_PIPELINE",
        database_type: str = "test",
        historical_folder_url: Optional[str] = None,
        current_folder_url: Optional[str] = None,
        log_fn: Optional[Callable[[str], None]] = None,
        show_progress: bool = False,
        historical_year: Optional[str] = None,
        current_year: Optional[str] = None,
    ):
        deliveries_config = DmsConfigLoader.get_distributor_deliveries_config()
        self._historical_folder_url = (
            historical_folder_url or deliveries_config["historical_folder_url"]
        )
        self._current_folder_url = (
            current_folder_url or deliveries_config["current_folder_url"]
        )
        self._dms_client = DmsClient()
        self._show_progress = show_progress

        hist, curr = historical_and_current_years(snapshot_date or date.today())
        self.HISTORICAL_YEAR = historical_year or hist
        self.CURRENT_YEAR = current_year or curr
        self.EXPECTED_FILES_HISTORICAL = _expected_files_for_year(self.HISTORICAL_YEAR)
        self.EXPECTED_FILES_CURRENT = _expected_files_for_year(self.CURRENT_YEAR)
        self.IGNORED_FILES = [
            f"دیتابیس تحویل به پخش ها - {self.HISTORICAL_YEAR}.xlsx",
            f"دیتابیس تحویل به پخش ها - {self.CURRENT_YEAR}.xlsx",
        ]
        self._historical_pattern = source_file_pattern_for_year(self.HISTORICAL_YEAR)
        self._current_pattern = source_file_pattern_for_year(self.CURRENT_YEAR)

        super().__init__(
            batch_id=batch_id,
            snapshot_date=snapshot_date,
            connection_factory=connection_factory,
            triggered_by=triggered_by,
            database_type=database_type,
            log_fn=log_fn,
        )

    @property
    def batch_type(self) -> str:
        return "DISTRIBUTOR_DELIVERIES"

    @property
    def publish_procedure(self) -> str:
        return self._qualify("etl_usp_build_distributor_deliveries_snapshot")

    @property
    def fact_table(self) -> str:
        return self._qualify("fact_DistributorDeliveries")

    def load_stage(
        self,
        batch_size: int = 10000,
        incremental: bool = False,
        single_date_only: bool = False,
        force_historical_reload: bool = False,
        **kwargs,
    ) -> None:
        del incremental, single_date_only, kwargs

        with self._handle_batch_failure("Load fact failed: "):
            self._ensure_snapshot_date()
            self._ensure_batch_created()

            with self._connection_factory.connection(self._database_type) as conn:
                cursor = conn.cursor()
                historical_row_count = count_fact_rows(
                    cursor, self.fact_table, self._historical_pattern
                )
                current_row_count = count_fact_rows(
                    cursor, self.fact_table, self._current_pattern
                )

            needs_full_reload = force_historical_reload or historical_row_count == 0

            if needs_full_reload:
                if force_historical_reload:
                    self._log("Force reload requested: erasing all fact rows.")
                else:
                    self._log(
                        f"No {self.HISTORICAL_YEAR} historical data in fact table; "
                        "loading full history."
                    )
                self._truncate_fact_table()
                self._log(
                    f"Loading historical ({self.HISTORICAL_YEAR}) and current "
                    f"({self.CURRENT_YEAR}) delivery files..."
                )
                df_historical = load_excel_files_from_dms(
                    dms_client=self._dms_client,
                    folder_url=self._historical_folder_url,
                    file_pattern=self.FILE_PATTERN,
                    expected_files=self.EXPECTED_FILES_HISTORICAL,
                    ignored_files=self.IGNORED_FILES,
                    persian_columns=self.PERSIAN_COLUMNS,
                    log_fn=self._log_fn,
                    log_label="historical files",
                )
                df_current = load_excel_files_from_dms(
                    dms_client=self._dms_client,
                    folder_url=self._current_folder_url,
                    file_pattern=self.FILE_PATTERN,
                    expected_files=self.EXPECTED_FILES_CURRENT,
                    ignored_files=self.IGNORED_FILES,
                    persian_columns=self.PERSIAN_COLUMNS,
                    log_fn=self._log_fn,
                    log_label="current files",
                )
                df = concat_delivery_dataframes([df_historical, df_current])
            else:
                self._log(
                    f"Keeping {historical_row_count:,} historical ({self.HISTORICAL_YEAR}) rows; "
                    f"replacing {current_row_count:,} current ({self.CURRENT_YEAR}) rows."
                )
                self._delete_current_year_fact_rows()
                self._log(f"Loading current ({self.CURRENT_YEAR}) delivery files...")
                df = load_excel_files_from_dms(
                    dms_client=self._dms_client,
                    folder_url=self._current_folder_url,
                    file_pattern=self.FILE_PATTERN,
                    expected_files=self.EXPECTED_FILES_CURRENT,
                    ignored_files=self.IGNORED_FILES,
                    persian_columns=self.PERSIAN_COLUMNS,
                    log_fn=self._log_fn,
                    log_label="current files",
                )

            fact_rows = transform_dataframe_to_fact_rows(df, self.PERSIAN_COLUMNS)
            if fact_rows:
                self._load_fact_rows_in_batches(fact_rows, batch_size)

        self._finish_success_if_standalone("Fact load complete")

    def _truncate_fact_table(self) -> None:
        with self._connection_factory.connection(self._database_type) as conn:
            cursor = conn.cursor()
            cursor.execute(f"DELETE FROM {self.fact_table}")
            conn.commit()

    def _delete_current_year_fact_rows(self) -> None:
        with self._connection_factory.connection(self._database_type) as conn:
            cursor = conn.cursor()
            deleted = delete_current_year_fact_rows(
                cursor, self.fact_table, current_year=self.CURRENT_YEAR
            )
            conn.commit()
            self._log(
                f"Removed {deleted:,} current-year ({self.CURRENT_YEAR}) fact rows before reload."
            )

    def _get_fact_insert_query(self) -> str:
        columns = ", ".join(self.FACT_COLUMNS)
        placeholders = ", ".join(["?"] * len(self.FACT_COLUMNS))
        return f"INSERT INTO {self.fact_table} ({columns}) VALUES ({placeholders})"

    def _load_fact_rows_in_batches(self, fact_rows: List[tuple], batch_size: int) -> None:
        insert_query = self._get_fact_insert_query()
        total_rows = len(fact_rows)
        self._log(f"Inserting {total_rows:,} rows into {self.fact_table}...")
        progress = (
            RowProgressBar(f"Load fact ({self.fact_table})", total=total_rows)
            if self._show_progress
            else None
        )

        try:
            for i in range(0, total_rows, batch_size):
                if self._interrupted:
                    raise KeyboardInterrupt("Process interrupted by user")
                batch = fact_rows[i : i + batch_size]
                batch_number = (i // batch_size) + 1
                self._load_batch_to_fact(batch, insert_query, batch_number)
                loaded = min(i + len(batch), total_rows)
                if progress is not None:
                    progress.update(loaded, "inserting")
                elif batch_number == 1 or batch_number % 10 == 0:
                    self._log(f"  loaded {loaded:,}/{total_rows:,} rows...")

            if progress is not None:
                progress.close("insert complete")
        except Exception:
            if progress is not None:
                progress.close("failed")
            raise

        self._log(
            f"Fact load complete: {total_rows:,} rows in "
            f"{(total_rows + batch_size - 1) // batch_size} batch(es)."
        )

    def _load_batch_to_fact(self, batch_data: List[tuple], insert_query: str, batch_number: int) -> None:
        with self._connection_factory.connection(self._database_type) as conn:
            cursor = conn.cursor()
            try:
                cursor.executemany(insert_query, batch_data)
                conn.commit()
            except Exception as exc:
                conn.rollback()
                raise Exception(
                    f"Failed to load batch {batch_number} into fact table: {exc}"
                ) from exc
