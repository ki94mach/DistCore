"""Pipeline for loading historical distributor deliveries from Dropbox files."""

import sys
import os
import warnings
from datetime import date, timedelta
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
    get_last_successful_ingestion_date,
    load_excel_files_from_dropbox,
    transform_dataframe_to_staging_rows,
)
from src.orchestrator.services.dropbox import DropboxClient
from src.orchestrator.services.dropbox.config import DropboxConfigLoader


class DistributorDeliveriesPipeline(TemplatePipeline):
    """
    Pipeline for loading historical distributor deliveries from Dropbox.
    
    This pipeline reads Excel files from a Dropbox folder, extracts factory names
    from filenames, and loads data from matching sheets into a staging table.
    
    Files follow the pattern: "دیتابیس تحویل به پخش ها - [Factory Name] - 1404"
    Each file should contain a sheet named after the factory.
    
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
    
    def load_stage(self, batch_size: int = 10000, incremental: bool = True, single_date_only: bool = False) -> None:
        """
        Load data from Dropbox files into staging table.
        
        Overrides TemplatePipeline.load_stage to handle Dropbox file reading instead of SQL extraction.
        
        Args:
            batch_size: Number of rows to insert per batch
            incremental: If True (default), only loads rows with delivery_date >= (last_successful_ingestion_date - 7 days).
                         If False, loads all rows regardless of date.
            single_date_only: Not used for Dropbox pipeline (kept for interface compatibility)
        """
        with self._handle_batch_failure("Load stage failed: "):
            self._ensure_snapshot_date()
            self._ensure_batch_created()
            
            min_delivery_date = self._get_min_delivery_date(incremental)
            df = load_excel_files_from_dropbox(
                dropbox_client=self._dropbox_client,
                shared_link=self._dropbox_shared_link,
                file_pattern=r'دیتابیس تحویل به پخش ها.*\.(xlsx|xls)$',
                expected_files=self.EXPECTED_FILES,
                ignored_files=self.IGNORED_FILES,
                persian_columns=self.PERSIAN_COLUMNS,
                header_row=7
            )
            
            self._prepare_staging_table()
            
            staging_rows = transform_dataframe_to_staging_rows(
                df=df,
                batch_id=self.batch_id,
                persian_columns=self.PERSIAN_COLUMNS,
                min_delivery_date=min_delivery_date
            )
            
            if not staging_rows:
                print("No rows to load after filtering. Exiting.")
                return
            
            self._load_staging_rows_in_batches(staging_rows, batch_size)
    
    def _get_min_delivery_date(self, incremental: bool) -> Optional[date]:
        """Determine minimum delivery date for incremental loading."""
        if not incremental:
            print("Full load mode: Loading all rows regardless of date")
            return None
        
        last_ingestion_date = get_last_successful_ingestion_date(
            self.batch_type,
            self._connection_factory,
            self.database_type
        )
        
        if last_ingestion_date:
            min_delivery_date = last_ingestion_date - timedelta(days=7)
            print(f"Incremental mode: Loading rows with delivery_date >= {min_delivery_date}")
            print(f"  (Last successful ingestion: {last_ingestion_date}, 7-day lookback)")
            return min_delivery_date
        else:
            print("Incremental mode: No previous successful ingestion found, loading all rows")
            return None
    
    def _load_staging_rows_in_batches(self, staging_rows: List[tuple], batch_size: int) -> None:
        """Load staging rows in batches using stored procedure."""
        total_batches = (len(staging_rows) + batch_size - 1) // batch_size
        print(f"\nLoading {len(staging_rows)} rows into staging table in {total_batches} batch(es)...")
        print("  (Using stored procedure with hybrid deduplication: row_hash for exact duplicates, business key for updates)")
        
        inserted_count = 0
        updated_count = 0
        
        try:
            for i in range(0, len(staging_rows), batch_size):
                if self._interrupted:
                    raise KeyboardInterrupt("Process interrupted by user")
                
                batch = staging_rows[i:i + batch_size]
                batch_number = (i // batch_size) + 1
                print(f"  Loading batch {batch_number}/{total_batches} ({len(batch)} rows)...", end=' ', flush=True)
                batch_inserted, batch_updated = self._load_batch_to_staging_with_merge(batch, batch_number)
                inserted_count += batch_inserted
                updated_count += batch_updated
                print(f"✓ (Inserted: {batch_inserted}, Updated: {batch_updated}, Skipped: {len(batch) - batch_inserted - batch_updated})")
        except KeyboardInterrupt:
            self._cleanup_partial_staging_data()
            raise
        
        print(f"\n✓ Successfully loaded all rows into staging table")
        print(f"  Total inserted: {inserted_count} new rows")
        print(f"  Total updated: {updated_count} existing rows (corrected/updated records)")
        print(f"  Total skipped: {len(staging_rows) - inserted_count - updated_count} exact duplicates")
    
    def _load_batch_to_staging_with_merge(self, batch_data: List[tuple], batch_number: int) -> Tuple[int, int]:
        """
        Load batch to staging using stored procedure with hybrid deduplication.
        
        Returns:
            Tuple of (inserted_count, updated_count)
        """
        procedure_name = '[Data].[etl_usp_merge_stage_distributor_deliveries]'
        inserted_count = 0
        updated_count = 0
        
        for row_data in batch_data:
            parameters = {
                'batch_id': row_data[0],
                'drug_code': row_data[1],
                'product_name': row_data[2],
                'distributor_name': row_data[3],
                'batch_number': row_data[4],
                'expiry_date': row_data[5],
                'delivered_quantity': row_data[6],
                'delivered_quantity_round_up': row_data[7],
                'delivered_quantity_round_down': row_data[8],
                'request_date': row_data[9],
                'delivery_date': row_data[10],
                'month': row_data[11],
                'warehouse_exit_letter_number': row_data[12],
                'warehouse_exit_quantity': row_data[13],
                'warehouse_exit_details': row_data[14],
                'receipt_status': row_data[15],
                'release_date': row_data[16],
                'days_between_delivery_release': row_data[17],
                'routine_delivery_quantity': row_data[18],
                'supply_chain_request_quantity': row_data[19],
                'factory_name': row_data[20],
                'company_name': row_data[21],
                'description': row_data[22],
                'source_file': row_data[23],
                'row_hash': row_data[24],
            }
            
            try:
                result = self._sql_executor.execute_procedure_with_output(
                    procedure_name=procedure_name,
                    parameters=parameters,
                    output_parameters=['action'],
                    database_type=self.database_type
                )
                
                action = result.get('action', '').upper() if result.get('action') else ''
                if action == 'INSERT':
                    inserted_count += 1
                elif action == 'UPDATE':
                    updated_count += 1
            except Exception as e:
                raise Exception(f"Failed to merge row in batch {batch_number}: {str(e)}") from e
        
        return (inserted_count, updated_count)
