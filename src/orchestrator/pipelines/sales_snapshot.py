from datetime import date
from pathlib import Path
from typing import List

from src.orchestrator.pipelines.utils import get_sql_folder_path, parse_select_statement, substitute_date_parameter
from src.orchestrator.services.sql_server_db.executors.sql_utils import read_sql_file, resolve_sql_file_path

from src.orchestrator.pipelines.inventory_base import InventoryPipelineBase


class SalesSnapshotPipeline(InventoryPipelineBase):
    """
    Pipeline for the sales snapshot.
    
    This pipeline demonstrates how to use SQL execution methods:
    - execute_procedure: Execute stored procedures
    - execute_procedure_with_output: Execute procedures with output parameters
    - execute_sql_file: Execute SQL files from the sql folder
    
    If batch_id is None, a new batch will be automatically created when run() is called.
    If snapshot_date is None, today's date will be used as the snapshot date.
    """

    def load_stage(
        self,
        batch_size: int = 10000,
        incremental: bool = False,
        single_date_only: bool = False,
    ) -> None:
        """
        Load sales staging data.

        Sales snapshots need month-to-date and rolling averages across recent history,
        so this pipeline loads a rolling six-month window ending on snapshot_date.
        """
        if incremental:
            raise ValueError(
                "Sales snapshots do not support incremental staging loads. "
                "Use a snapshot date to load the rolling six-month window."
            )

        with self._handle_batch_failure("Load stage failed: "):
            self._ensure_snapshot_date()
            self._ensure_batch_created()

            start_date = self._six_month_window_start(self.snapshot_date)
            extract_query = self._build_extract_query_for_window(start_date, self.snapshot_date)
            self._prepare_staging_table()

            try:
                self._extract_and_load_batches(extract_query, batch_size)
            except KeyboardInterrupt:
                self._cleanup_partial_staging_data()
                raise

    def _six_month_window_start(self, snapshot_date: date) -> date:
        snapshot_month = date(snapshot_date.year, snapshot_date.month, 1)
        month_index = snapshot_month.month - 1
        start_month_index = month_index - 5
        start_year = snapshot_month.year + (start_month_index // 12)
        start_month = (start_month_index % 12) + 1
        return date(start_year, start_month, 1)

    def _build_extract_query_for_window(self, start_date: date, end_date: date) -> str:
        sql_folder = get_sql_folder_path(Path(__file__))
        sql_path = resolve_sql_file_path(self.extract_sql_path, sql_folder)
        query_template = read_sql_file(sql_path)

        select_statement = parse_select_statement(query_template)
        query = substitute_date_parameter(select_statement, 'since', start_date)

        end_date_str = end_date.strftime("'%Y-%m-%d'")
        trimmed = query.rstrip().rstrip(';')
        return f"{trimmed}\n  AND [FKDate] <= {end_date_str}"

    @property
    def batch_type(self) -> str:
        return 'SALES_SNAPSHOT'

    @property
    def extract_sql_path(self) -> str:
        return '20_etl/sales/extract.sql'

    @property
    def publish_procedure(self) -> str:
        return '[Data].[etl_usp_build_sales_snapshot]'

    @property
    def staging_table(self) -> str:
        return '[Data].[stg_Sales]'

    @property
    def staging_columns(self) -> List[str]:
        return [
            'batch_id',
            'distributor_id',
            'center_id',
            'product_id',
            'product_batch_no',
            'as_of_datetime',
            'sales_qty',
        ]

    def transform_row_to_staging_data(self, row: tuple, columns: List[str]) -> tuple:
        row_dict = dict(zip(columns, row))
        return (
            self.batch_id,
            row_dict.get('distributor_id'),
            row_dict.get('center_id'),
            row_dict.get('product_id'),
            row_dict.get('product_batch_no'),
            row_dict.get('as_of_datetime'),
            row_dict.get('sales_qty'),
        )
