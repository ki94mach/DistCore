"""Pipeline for loading historical distributor deliveries from Dropbox files."""

from datetime import date
from typing import List, Optional
import pandas as pd

from src.orchestrator.pipelines.pipeline_template import TemplatePipeline
from src.orchestrator.pipelines.utils import (
    parse_excel_date,
    safe_int,
)
from src.orchestrator.services.dropbox import DropboxClient
from src.orchestrator.services.dropbox.config import DropboxConfigLoader


class DistributorDeliveriesPipeline(TemplatePipeline):
    """
    Pipeline for loading historical distributor deliveries from Dropbox.
    
    This pipeline reads Excel files from a Dropbox folder, concatenates them,
    and loads the data into a staging table.
    
    Files follow the pattern: "دیتابیس تحویل به پخش ها - [Company Name] - 1404"
    
    If batch_id is None, a new batch will be automatically created when run() is called.
    If snapshot_date is None, today's date will be used as the snapshot date.
    """
    
    # Persian column names from the source files
    PERSIAN_COLUMNS = [
        'کد دارو',  # Drug Code
        'کالا',  # Product
        'نام پخش',  # Distributor Name
        'شماره بچ',  # Batch Number
        'تاریخ انقضاء',  # Expiry Date
        'تعداد تحویلی',  # Delivered Quantity
        'تعداد تحویلی رند بالا',  # Delivered Quantity Round Up
        'تعداد تحویلی رند پایین',  # Delivered Quantity Round Down
        'تاریخ درخواست',  # Request Date
        'تاریخ تحویل',  # Delivery Date
        'ماه',  # Month
        'شماره نامه خروج از انبار',  # Warehouse Exit Letter Number
        'تعداد خروج از انبار',  # Warehouse Exit Quantity
        'جزئیات خروج از انبار',  # Warehouse Exit Details
        'وضعیت رسید',  # Receipt Status
        'تاریخ ریلیز',  # Release Date
        'تعداد روز بین تاریخ تحویلی و ریلیز',  # Days Between Delivery and Release
        'تعداد تحویل روتین',  # Routine Delivery Quantity
        'تعداد درخواست زنجیره تامین',  # Supply Chain Request Quantity
        'کارخانه',  # Factory/Manufacturer
        'توضیحات',  # Description
    ]
    
    def __init__(
        self,
        batch_id: Optional[int],
        snapshot_date: Optional[date] = None,
        connection_factory=None,
        triggered_by: str = 'PYTHON_PIPELINE',
        database_type: str = 'test',
        dropbox_access_token: Optional[str] = None,
    ):
        """
        Initialize the distributor deliveries pipeline.
        
        Args:
            batch_id: Optional batch ID (will be created if None)
            snapshot_date: Optional snapshot date (defaults to today)
            connection_factory: Optional database connection factory
            triggered_by: Who/what triggered this pipeline
            database_type: Database type ('source' or 'test')
            dropbox_access_token: Optional Dropbox access token
        
        Note:
            The Dropbox folder path is read from src/orchestrator/config/dropbox.yml
        """
        # Load folder path from config file
        self._dropbox_folder_path = DropboxConfigLoader.get_distributor_deliveries_folder()
        
        self._dropbox_client = DropboxClient(access_token=dropbox_access_token)
        
        super().__init__(
            batch_id=batch_id,
            snapshot_date=snapshot_date,
            connection_factory=connection_factory,
            triggered_by=triggered_by,
            database_type=database_type,
        )
    
    @property
    def batch_type(self) -> str:
        return 'DISTRIBUTOR_DELIVERIES'
    
    @property
    def extract_sql_path(self) -> str:
        """
        Not used for Dropbox-based pipeline, but required by TemplatePipeline.
        Returns a dummy path.
        """
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
        ]
    
    def transform_row_to_staging_data(self, row: tuple, columns: List[str]) -> tuple:
        """
        Transform SQL row to staging data.
        
        Note: This is required by TemplatePipeline but not used for Dropbox pipeline.
        The actual transformation happens in _transform_dataframe_to_staging_rows.
        """
        # This method is not used for Dropbox-based extraction
        # but required by TemplatePipeline abstract method
        raise NotImplementedError("This pipeline uses DataFrame transformation, not SQL row transformation")
    
    def _transform_dataframe_to_staging_rows(self, df: pd.DataFrame) -> List[tuple]:
        """
        Transform DataFrame rows to staging table tuples.
        
        Args:
            df: DataFrame with Persian column names
            
        Returns:
            List of tuples ready for insertion into staging table
        """
        staging_rows = []
        
        for _, row in df.iterrows():
            # Company name is not extracted from filename
            source_file = row.get('source_file', '')
            company_name = None
            
            # Parse dates using utility function
            delivery_date = parse_excel_date(row.get('تاریخ تحویل'))
            request_date = parse_excel_date(row.get('تاریخ درخواست'))
            expiry_date = parse_excel_date(row.get('تاریخ انقضاء'))
            release_date = parse_excel_date(row.get('تاریخ ریلیز'))
            
            # Convert quantities to integers using utility function
            delivered_qty = safe_int(row.get('تعداد تحویلی'))
            delivered_qty_round_up = safe_int(row.get('تعداد تحویلی رند بالا'))
            delivered_qty_round_down = safe_int(row.get('تعداد تحویلی رند پایین'))
            warehouse_exit_qty = safe_int(row.get('تعداد خروج از انبار'))
            routine_delivery_qty = safe_int(row.get('تعداد تحویل روتین'))
            supply_chain_request_qty = safe_int(row.get('تعداد درخواست زنجیره تامین'))
            days_between_delivery_release = safe_int(row.get('تعداد روز بین تاریخ تحویلی و ریلیز'))
            
            # Extract month (could be numeric or string)
            month = row.get('ماه')
            if pd.notna(month):
                try:
                    month = int(month)
                except:
                    month = None
            else:
                month = None
            
            staging_row = (
                self.batch_id,
                str(row.get('کد دارو', '')),  # drug_code
                str(row.get('کالا', '')),  # product_name
                str(row.get('نام پخش', '')),  # distributor_name
                str(row.get('شماره بچ', '')),  # batch_number
                expiry_date,  # expiry_date
                delivered_qty,  # delivered_quantity
                delivered_qty_round_up,  # delivered_quantity_round_up
                delivered_qty_round_down,  # delivered_quantity_round_down
                request_date,  # request_date
                delivery_date,  # delivery_date
                month,  # month
                str(row.get('شماره نامه خروج از انبار', '')),  # warehouse_exit_letter_number
                warehouse_exit_qty,  # warehouse_exit_quantity
                str(row.get('جزئیات خروج از انبار', '')),  # warehouse_exit_details
                str(row.get('وضعیت رسید', '')),  # receipt_status
                release_date,  # release_date
                days_between_delivery_release,  # days_between_delivery_release
                routine_delivery_qty,  # routine_delivery_quantity
                supply_chain_request_qty,  # supply_chain_request_quantity
                str(row.get('کارخانه', '')),  # factory_name
                company_name,  # company_name (extracted from filename)
                str(row.get('توضیحات', '')),  # description
                source_file,  # source_file
            )
            
            staging_rows.append(staging_row)
        
        return staging_rows
    
    def load_stage(self, batch_size: int = 10000, incremental: bool = False, single_date_only: bool = False) -> None:
        """
        Load data from Dropbox files into staging table.
        
        Overrides TemplatePipeline.load_stage to handle Dropbox file reading instead of SQL extraction.
        
        Args:
            batch_size: Number of rows to insert per batch
            incremental: Not used for Dropbox pipeline (kept for interface compatibility)
            single_date_only: Not used for Dropbox pipeline (kept for interface compatibility)
        """
        with self._handle_batch_failure("Load stage failed: "):
            self._ensure_snapshot_date()
            self._ensure_batch_created()
            
            # Pattern to match files: "دیتابیس تحویل به پخش ها - [Company] - 1404"
            file_pattern = r'دیتابیس تحویل به پخش ها.*\.(xlsx|xls)$'
            
            # Download and concatenate all Excel files from Dropbox
            # Headers are on row 8 (0-indexed: 7), data starts from row 9 (0-indexed: 8)
            print(f"Downloading files from Dropbox folder: {self._dropbox_folder_path}")
            df = self._dropbox_client.concatenate_excel_files(
                folder_path=self._dropbox_folder_path,
                file_pattern=file_pattern,
                header_row=7,  # Row 8 (1-indexed) = index 7 (0-indexed)
                add_source_file_column=True,
                sheet_name='تحویل به پخش ها'
            )
            
            print(f"Loaded {len(df)} rows from {df['source_file'].nunique()} files")
            
            # Prepare staging table (uses TemplatePipeline method)
            self._prepare_staging_table()
            
            # Transform and load in batches
            staging_rows = self._transform_dataframe_to_staging_rows(df)
            
            # Use TemplatePipeline's insert query method
            insert_query = self._get_staging_insert_query()
            
            try:
                for i in range(0, len(staging_rows), batch_size):
                    if self._interrupted:
                        raise KeyboardInterrupt("Process interrupted by user")
                    
                    batch = staging_rows[i:i + batch_size]
                    batch_number = (i // batch_size) + 1
                    self._load_batch_to_staging(batch, insert_query, batch_number)
                    print(f"Loaded batch {batch_number} ({len(batch)} rows)")
            except KeyboardInterrupt:
                self._cleanup_partial_staging_data()
                raise
    

