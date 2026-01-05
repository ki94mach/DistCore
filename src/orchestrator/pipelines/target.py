from datetime import date
from pathlib import Path
from typing import List

from src.orchestrator.pipelines.pipeline_template import TemplatePipeline
from src.orchestrator.pipelines.utils import (
    get_sql_folder_path,
    parse_select_statement,
    substitute_date_parameter,
    substitute_jalali_year_parameter,
)
from src.orchestrator.services.sql_server_db.executors.sql_utils import (
    read_sql_file,
    resolve_sql_file_path,
)


class TargetPipeline(TemplatePipeline):
    """
    Pipeline for the target data.
    
    This pipeline extracts target quantities from [DWOrchid].[dbo].[FactTarget]
    filtered by the current Jalali year, loads them into staging, and publishes
    them to the snapshot table.
    
    If batch_id is None, a new batch will be automatically created when run() is called.
    If snapshot_date is None, today's date will be used as the snapshot date.
    """
    
    def _build_extract_query(self, since_date, use_equality_filter: bool) -> str:
        """
        Override to inject Jalali year calculation directly into the query.
        """
        sql_folder = get_sql_folder_path(Path(__file__))
        sql_path = resolve_sql_file_path(self.extract_sql_path, sql_folder)
        query_template = read_sql_file(sql_path)
        
        select_statement = parse_select_statement(query_template)
        
        # Substitute Jalali year parameter with calculated value
        current_date = date.today()
        query = substitute_jalali_year_parameter(select_statement, current_date, 'current_jalali_year')
        
        # Also substitute @since parameter (even though it's not used for target)
        query = substitute_date_parameter(query, 'since', since_date)
        
        return query
    
    @property
    def batch_type(self) -> str:
        return 'TARGET'

    @property
    def extract_sql_path(self) -> str:
        return '20_etl/target/extract.sql'

    @property
    def publish_procedure(self) -> str:
        return '[Data].[etl_usp_build_target_snapshot]'

    @property
    def staging_table(self) -> str:
        return '[Data].[stg_Target]'

    @property
    def staging_columns(self) -> List[str]:
        return [
            'batch_id',
            'product_id',
            'year',
            'month',
            'target_quantity',
            'as_of_datetime',
        ]

    def transform_row_to_staging_data(self, row: tuple, columns: List[str]) -> tuple:
        row_dict = dict(zip(columns, row))
        return (
            self.batch_id,
            row_dict.get('product_id'),
            row_dict.get('year'),
            row_dict.get('month'),
            row_dict.get('target_quantity'),
            self.snapshot_date,  # Use snapshot_date as as_of_datetime
        )

