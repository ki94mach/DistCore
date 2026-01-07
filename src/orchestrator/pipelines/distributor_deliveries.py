"""Pipeline for loading historical distributor deliveries from Dropbox files."""

import sys
import os
import warnings
from datetime import date, timedelta
from typing import List, Optional, Tuple
import pandas as pd

# Suppress openpyxl warnings BEFORE importing anything that uses it
warnings.filterwarnings('ignore', category=UserWarning, module='openpyxl')
warnings.filterwarnings('ignore', message='.*Data Validation.*')
warnings.filterwarnings('ignore', message='.*Print area.*')

# Set UTF-8 encoding for Windows terminal to display Farsi characters
if sys.platform == 'win32':
    # Set console output encoding to UTF-8
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
    # Also set environment variable for subprocesses
    os.environ['PYTHONIOENCODING'] = 'utf-8'

from src.orchestrator.pipelines.pipeline_template import TemplatePipeline
from src.orchestrator.pipelines.utils import (
    parse_excel_date,
    safe_int,
    calculate_row_hash,
    check_row_hash_exists,
    get_last_successful_ingestion_date,
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
    
    # Expected files to check for (extracted from local Dropbox paths)
    # These are checked for existence, but pattern matching still allows future files
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
    
    # Files to ignore (files that match pattern but should be skipped)
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
        
        Note:
            The Dropbox shared link can be provided directly or read from src/orchestrator/config/dropbox.yml
        """
        # Load shared link from config file if not provided
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
            'row_hash',
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
    
    def _calculate_row_hash(self, row: pd.Series) -> bytes:
        """
        Calculate SHA-256 hash of all data columns for distributor deliveries.
        
        Hash includes all file data columns to detect duplicate rows regardless of batch or source file.
        
        Args:
            row: DataFrame row with Persian column names
            
        Returns:
            SHA-256 hash as bytes (32 bytes)
        """
        # Extract all data values in consistent order
        hash_values = [
            row.get('کد دارو', ''),  # drug_code
            row.get('کالا', ''),  # product_name
            row.get('نام پخش', ''),  # distributor_name
            row.get('شماره بچ', ''),  # batch_number
            parse_excel_date(row.get('تاریخ انقضاء')),  # expiry_date
            safe_int(row.get('تعداد تحویلی')),  # delivered_quantity
            safe_int(row.get('تعداد تحویلی رند بالا')),  # delivered_quantity_round_up
            safe_int(row.get('تعداد تحویلی رند پایین')),  # delivered_quantity_round_down
            parse_excel_date(row.get('تاریخ درخواست')),  # request_date
            parse_excel_date(row.get('تاریخ تحویل')),  # delivery_date
            row.get('ماه', ''),  # month
            row.get('شماره نامه خروج از انبار', ''),  # warehouse_exit_letter_number
            safe_int(row.get('تعداد خروج از انبار')),  # warehouse_exit_quantity
            row.get('جزئیات خروج از انبار', ''),  # warehouse_exit_details
            row.get('وضعیت رسید', ''),  # receipt_status
            parse_excel_date(row.get('تاریخ ریلیز')),  # release_date
            safe_int(row.get('تعداد روز بین تاریخ تحویلی و ریلیز')),  # days_between_delivery_release
            safe_int(row.get('تعداد تحویل روتین')),  # routine_delivery_quantity
            safe_int(row.get('تعداد درخواست زنجیره تامین')),  # supply_chain_request_quantity
            row.get('کارخانه', ''),  # factory_name
            row.get('توضیحات', ''),  # description
        ]
        
        return calculate_row_hash(hash_values)
    
    def _transform_dataframe_to_staging_rows(self, df: pd.DataFrame, min_delivery_date: Optional[date] = None) -> List[tuple]:
        """
        Transform DataFrame rows to staging table tuples.
        
        Args:
            df: DataFrame with Persian column names
            min_delivery_date: Optional minimum delivery_date filter (for incremental loading)
            
        Returns:
            List of tuples ready for insertion into staging table
        """
        staging_rows = []
        total_rows = len(df)
        filtered_count = 0
        
        # Show progress every 1000 rows
        progress_interval = max(1000, total_rows // 10)
        
        for idx, (_, row) in enumerate(df.iterrows(), 1):
            # Show progress
            if idx % progress_interval == 0 or idx == total_rows:
                print(f"  Transforming row {idx}/{total_rows} ({idx*100//total_rows}%)...", end='\r', flush=True)
            
            # Parse delivery_date for filtering
            delivery_date = parse_excel_date(row.get('تاریخ تحویل'))
            
            # Filter by delivery_date if incremental loading
            if min_delivery_date is not None:
                if delivery_date is None or delivery_date < min_delivery_date:
                    filtered_count += 1
                    continue
            
            # Company name is not extracted from filename
            source_file = row.get('source_file', '')
            company_name = None
            
            # Parse other dates using utility function
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
            
            # Calculate row hash for deduplication
            row_hash = self._calculate_row_hash(row)
            
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
                row_hash,  # row_hash
            )
            
            staging_rows.append(staging_row)
        
        # Clear progress line
        print(" " * 60, end='\r', flush=True)
        if filtered_count > 0:
            print(f"  Filtered out {filtered_count} rows outside date range")
        return staging_rows
    
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
            
            # Determine date filter for incremental loading
            min_delivery_date = None
            if incremental:
                last_ingestion_date = get_last_successful_ingestion_date(
                    self.batch_type,
                    self._connection_factory,
                    self.database_type
                )
                if last_ingestion_date:
                    # 7-day lookback window: load rows from (last_ingestion_date - 7 days) onwards
                    min_delivery_date = last_ingestion_date - timedelta(days=7)
                    print(f"Incremental mode: Loading rows with delivery_date >= {min_delivery_date}")
                    print(f"  (Last successful ingestion: {last_ingestion_date}, 7-day lookback)")
                else:
                    print("Incremental mode: No previous successful ingestion found, loading all rows")
            else:
                print("Full load mode: Loading all rows regardless of date")
            
            # Pattern to match files: "دیتابیس تحویل به پخش ها - [Company] - 1404"
            file_pattern = r'دیتابیس تحویل به پخش ها.*\.(xlsx|xls)$'
            
            # Download and concatenate all Excel files from Dropbox
            # Headers are on row 8 (0-indexed: 7), data starts from row 9 (0-indexed: 8)
            print(f"Downloading files from Dropbox shared link: {self._dropbox_shared_link}")
            print("Checking for expected files...")
            df = self._dropbox_client.concatenate_excel_files(
                file_pattern=file_pattern,
                header_row=7,  # Row 8 (1-indexed) = index 7 (0-indexed)
                add_source_file_column=True,
                sheet_name='تحویل به پخش ها',
                expected_files=self.EXPECTED_FILES,
                ignored_files=self.IGNORED_FILES
            )
            
            loaded_files = df['source_file'].unique().tolist() if 'source_file' in df.columns else []
            print(f"\n✓ Successfully loaded {len(df)} rows from {len(loaded_files)} file(s):")
            for filename in sorted(loaded_files):
                file_rows = len(df[df['source_file'] == filename])
                print(f"  - {filename} ({file_rows} rows)")
            
            # Prepare staging table (uses TemplatePipeline method)
            print("\nPreparing staging table...")
            self._prepare_staging_table()
            print("✓ Staging table prepared")
            
            # Transform and filter by date
            print(f"\nTransforming {len(df)} rows to staging format...")
            staging_rows = self._transform_dataframe_to_staging_rows(df, min_delivery_date=min_delivery_date)
            print(f"✓ Transformed {len(staging_rows)} rows (after date filtering)")
            
            if not staging_rows:
                print("No rows to load after filtering. Exiting.")
                return
            
            # Use stored procedure for MERGE with hybrid deduplication (row_hash + business key)
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
        Load batch to staging using stored procedure with hybrid deduplication and return counts.
        
        Hybrid logic (implemented in stored procedure):
        1. Check row_hash first - if exists, skip (exact duplicate)
        2. If row_hash doesn't exist, use MERGE on business key
        3. MERGE will UPDATE if business key matches, INSERT otherwise
        
        Args:
            batch_data: List of tuples with staging row data (includes row_hash as last element)
            batch_number: Batch number for logging
            
        Returns:
            Tuple of (inserted_count, updated_count)
        """
        procedure_name = '[Data].[etl_usp_merge_stage_distributor_deliveries]'
        inserted_count = 0
        updated_count = 0
        
        for row_data in batch_data:
            # Map tuple data to parameter dictionary
            # row_data order matches staging_columns order
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
                'row_hash': row_data[24],  # row_hash is last element
            }
            
            try:
                # Execute stored procedure with output parameter
                result = self._sql_executor.execute_procedure_with_output(
                    procedure_name=procedure_name,
                    parameters=parameters,
                    output_parameters=['action'],
                    database_type=self.database_type
                )
                
                action = result.get('action', '')
                if action:
                    action = action.upper()
                    if action == 'INSERT':
                        inserted_count += 1
                    elif action == 'UPDATE':
                        updated_count += 1
                    # 'SKIP' is handled by stored procedure, no count needed
                else:
                    # If action is None/empty, assume INSERT (shouldn't happen, but handle gracefully)
                    inserted_count += 1
                
            except Exception as e:
                raise Exception(
                    f"Failed to merge row in batch {batch_number}: {str(e)}"
                ) from e
        
        return (inserted_count, updated_count)
    

