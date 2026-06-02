from typing import List

from src.orchestrator.pipelines.pipeline_template import TemplatePipeline


class DistributorInventoryPipeline(TemplatePipeline):
    """
    Pipeline for the distributor inventory.
    
    This pipeline demonstrates how to use SQL execution methods:
    - execute_procedure: Execute stored procedures
    - execute_procedure_with_output: Execute procedures with output parameters
    - execute_sql_file: Execute SQL files from the sql folder
    
    If batch_id is None, a new batch will be automatically created when run() is called.
    If snapshot_date is None, today's date will be used as the snapshot date.
    """
    
    @property
    def batch_type(self) -> str:
        return 'DISTRIBUTOR_INVENTORY'

    @property
    def extract_sql_path(self) -> str:
        return '20_etl/distributor_inventory/extract.sql'

    @property
    def publish_procedure(self) -> str:
        return '[Data].[etl_usp_build_distributor_inventory_snapshot]'

    @property
    def staging_table(self) -> str:
        return '[Data].[stg_DistributorInventory]'

    @property
    def snapshot_table(self) -> str:
        return '[Data].[snp_DistributorInventorySnapshot]'

    @property
    def staging_columns(self) -> List[str]:
        return [
            'batch_id',
            'product_id',
            'distributor_id',
            'center_id',
            'product_batch_no',
            'as_of_datetime',
            'on_hand_qty',
        ]

    def transform_row_to_staging_data(self, row: tuple, columns: List[str]) -> tuple:
        row_dict = dict(zip(columns, row))
        return (
            self.batch_id,
            row_dict.get('product_id'),
            row_dict.get('distributor_id'),
            row_dict.get('center_id'),
            row_dict.get('product_batch_no'),
            row_dict.get('as_of_datetime'),
            row_dict.get('on_hand_qty'),
        )
