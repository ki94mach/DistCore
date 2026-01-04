from typing import List

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

        Sales snapshots need month-to-date and rolling averages across all staging rows,
        so this pipeline always performs a full load. Use single_date_only for
        backfills that intentionally limit the staging window.
        """
        if incremental and not single_date_only:
            raise ValueError(
                "Sales snapshots require full staging loads; set incremental=False "
                "or use single_date_only for scoped backfills."
            )
        super().load_stage(
            batch_size=batch_size,
            incremental=False,
            single_date_only=single_date_only,
        )

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
