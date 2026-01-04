from datetime import date
from pathlib import Path

from src.orchestrator.pipelines.inventory_base import InventoryPipelineBase
from src.orchestrator.pipelines.utils import (
    get_sql_folder_path,
    parse_select_statement,
    substitute_date_parameter,
)
from src.orchestrator.services.sql_server_db.executors.sql_utils import (
    read_sql_file,
    resolve_sql_file_path,
)


class SalesSnapshotPipelineBase(InventoryPipelineBase):
    """
    Template base for sales snapshot pipelines with rolling window staging logic.
    """

    def load_stage(
        self,
        batch_size: int = 10000,
        incremental: bool = False,
        single_date_only: bool = False,
    ) -> None:
        """
        Load sales staging data for a rolling six-month window ending on snapshot_date.
        """
        if incremental or single_date_only:
            raise ValueError(
                "Sales snapshots do not support incremental or single-date-only staging "
                "loads. Provide a snapshot date to load the rolling six-month window."
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
