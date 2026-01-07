"""Pipeline for loading historical distributor deliveries from Dropbox files."""

import sys
import os
import warnings
from datetime import date
from typing import List, Optional, Tuple

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
    load_excel_files_from_dropbox,
    transform_dataframe_to_staging_rows,
)
from src.orchestrator.services.dropbox import DropboxClient
from src.orchestrator.services.dropbox.config import DropboxConfigLoader


class DistributorDeliveriesPipeline(TemplatePipeline):
    """
    Pipeline for loading historical distributor deliveries from Dropbox.
    
    This pipeline reads Excel files from a Dropbox folder, extracts factory names
    from filenames, and loads data from matching Excel tables (ListObjects) into a staging table.
    
    Files follow the pattern: "دیتابیس تحویل به پخش ها - [Factory Name] - 1404"
    Each file should contain an Excel table named after the factory.
    
    If batch_id is None, a new batch will be automatically created when run() is called.
    If snapshot_date is None, today's date will be used as the snapshot date.
    """
    
    # Expected files to check for
    EXPECTED_FILES = [
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
    
    # Files to ignore
    IGNORED_FILES = [
        'دیتابیس تحویل به پخش ها - 1404.xlsx',  # File without company name
    ]
    
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
        shared_link: Optional[str] = None,
    ):
        """
        Initialize the distributor deliveries pipeline.
        
        Args:
            batch_id: Optional batch ID (will be created if None)
            snapshot_date: Optional snapshot date (defaults to today)
            connection_factory: Optional database connection factory
            triggered_by: Who/what triggered this pipeline
            database_type: Database type ('source' or 'test')
            shared_link: Optional Dropbox shared link. If not provided, will be loaded from config.
        """
        if shared_link is None:
            shared_link = DropboxConfigLoader.get_distributor_deliveries_folder()
        
        self._dropbox_shared_link = shared_link
        self._dropbox_client = DropboxClient(shared_link=shared_link)
        
        super().__init__(
            batch_id=batch_id,
            snapshot_date=snapshot_date,
            connection_factory=connection_factory,
            triggered_by=triggered_by,
            database_type=database_type,
        )
    
    # TemplatePipeline required properties
    @property
    def batch_type(self) -> str:
        return 'DISTRIBUTOR_DELIVERIES'
    
    @property
    def extract_sql_path(self) -> str:
        """Not used for Dropbox-based pipeline, but required by TemplatePipeline."""
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
        """
        Transform SQL row to staging data.
        
        Note: This is required by TemplatePipeline but not used for Dropbox pipeline.
        The actual transformation happens in utils functions.
        """
        raise NotImplementedError("This pipeline uses DataFrame transformation, not SQL row transformation")
    
    def load_stage(self, batch_size: int = 10000, incremental: bool = False, single_date_only: bool = False) -> None:
        """
        Load data from Dropbox files into staging table.
        
        Overrides TemplatePipeline.load_stage to handle Dropbox file reading instead of SQL extraction.
        Always performs a full import of all data (incremental parameter is ignored).
        
        Args:
            batch_size: Number of rows to insert per batch
            incremental: Ignored - always performs full import (kept for interface compatibility)
            single_date_only: Not used for Dropbox pipeline (kept for interface compatibility)
        """
        with self._handle_batch_failure("Load stage failed: "):
            self._ensure_snapshot_date()
            self._ensure_batch_created()
            
            print("Full load mode: Loading all rows regardless of date")
            df = load_excel_files_from_dropbox(
                dropbox_client=self._dropbox_client,
                shared_link=self._dropbox_shared_link,
                file_pattern=r'دیتابیس تحویل به پخش ها.*\.(xlsx|xls)$',
                expected_files=self.EXPECTED_FILES,
                ignored_files=self.IGNORED_FILES,
                persian_columns=self.PERSIAN_COLUMNS,
                header_row=7
            )
            
            # Delete all rows from staging table (full refresh)
            self._truncate_staging_table()
            
            staging_rows = transform_dataframe_to_staging_rows(
                df=df,
                batch_id=self.batch_id,
                persian_columns=self.PERSIAN_COLUMNS
            )
            
            if not staging_rows:
                print("No rows to load. Exiting.")
                return
            
            self._load_staging_rows_in_batches(staging_rows, batch_size)
    
    def _truncate_staging_table(self) -> None:
        """Delete all rows from staging table (full refresh)."""
        delete_query = f"DELETE FROM {self.staging_table}"
        
        with self._connection_factory.connection(self._database_type) as conn:
            cursor = conn.cursor()
            cursor.execute(delete_query)
            deleted_count = cursor.rowcount
            conn.commit()
            print(f"Deleted {deleted_count} existing rows from staging table")
    
    def _load_staging_rows_in_batches(self, staging_rows: List[tuple], batch_size: int) -> None:
        """Load staging rows in batches using simple INSERT."""
        total_batches = (len(staging_rows) + batch_size - 1) // batch_size
        print(f"\nLoading {len(staging_rows)} rows into staging table in {total_batches} batch(es)...")
        
        insert_query = self._get_staging_insert_query()
        
        try:
            for i in range(0, len(staging_rows), batch_size):
                if self._interrupted:
                    raise KeyboardInterrupt("Process interrupted by user")
                
                batch = staging_rows[i:i + batch_size]
                batch_number = (i // batch_size) + 1
                print(f"  Loading batch {batch_number}/{total_batches} ({len(batch)} rows)...", end=' ', flush=True)
                self._load_batch_to_staging(batch, insert_query, batch_number)
                print(f"✓")
        except KeyboardInterrupt:
            self._cleanup_partial_staging_data()
            raise
        
        print(f"\n✓ Successfully loaded {len(staging_rows)} rows into staging table")
    
    def _load_batch_to_staging(self, batch_data: List[tuple], insert_query: str, batch_number: int) -> None:
        """Load batch to staging using simple INSERT."""
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
