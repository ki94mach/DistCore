"""Dropbox and Excel file processing utilities for pipelines."""

import io
import re
import unicodedata
from datetime import date
from typing import List, Optional, Tuple
import pandas as pd
import openpyxl

from src.orchestrator.pipelines.utils.excel_utils import parse_excel_date, safe_int
from src.orchestrator.services.dropbox import DropboxClient


def extract_factory_name_from_filename(filename: str) -> Optional[str]:
    """
    Extract factory name from filename pattern: "دیتابیس تحویل به پخش ها - [Factory Name] - 1404.xlsx"
    
    Args:
        filename: Excel file name
        
    Returns:
        Factory name or None if pattern doesn't match
    """
    pattern = r'دیتابیس تحویل به پخش ها\s*-\s*([^-]+?)\s*-\s*\d+\.(xlsx|xls)$'
    match = re.search(pattern, filename)
    if match:
        return match.group(1).strip()
    return None


def find_matching_table(
    dropbox_client: DropboxClient,
    file_info: dict,
    factory_name: str,
    shared_link: str
) -> Optional[Tuple[str, str]]:
    """
    Find the Excel table (ListObject) in an Excel file that matches the factory name.
    
    Args:
        dropbox_client: DropboxClient instance
        file_info: File info dictionary from list_files
        factory_name: Factory name to match
        shared_link: Dropbox shared link
        
    Returns:
        Tuple of (sheet_name, table_name) if found, None otherwise
    """
    file_content = dropbox_client.download_file(file_info['path'], shared_link=shared_link)
    # Load workbook without read_only to access tables (tables are not available in read-only mode)
    workbook = openpyxl.load_workbook(io.BytesIO(file_content), read_only=False)
    available_sheets = workbook.sheetnames
    
    # Normalize factory name
    factory_stripped = factory_name.strip()
    
    # Remove zero-width characters from factory name
    factory_cleaned = ''.join(c for c in factory_stripped if unicodedata.category(c) != 'Cf')
    
    # Try to find matching table across all sheets
    for sheet_name in available_sheets:
        worksheet = workbook[sheet_name]
        
        # Access tables from worksheet (available in read/write mode)
        if not worksheet.tables:
            continue
        
        # Check all tables in this sheet
        for table_name, table in worksheet.tables.items():
            table_stripped = table_name.strip()
            
            # Remove zero-width characters from table name
            table_cleaned = ''.join(c for c in table_stripped if unicodedata.category(c) != 'Cf')
            
            # Strategy 1: Exact match without normalization (fastest, most likely to work)
            if table_stripped == factory_stripped:
                workbook.close()
                return (sheet_name, table_name)
            
            # Strategy 2: Exact match with cleaned versions (no zero-width chars)
            if table_cleaned == factory_cleaned:
                workbook.close()
                return (sheet_name, table_name)
            
            # Strategy 2.5: Match after removing spaces (handles cases like "اسپاد فارمد" vs "اسپادفارمد")
            table_no_spaces = table_cleaned.replace(' ', '').replace('\u200C', '').replace('\u200D', '')
            factory_no_spaces = factory_cleaned.replace(' ', '').replace('\u200C', '').replace('\u200D', '')
            if table_no_spaces == factory_no_spaces:
                workbook.close()
                return (sheet_name, table_name)
            
            # Strategy 3: Try different normalization forms
            for norm_form in ['NFC', 'NFD', 'NFKC', 'NFKD']:
                normalized_table = unicodedata.normalize(norm_form, table_stripped)
                normalized_factory = unicodedata.normalize(norm_form, factory_stripped)
                
                # Exact match
                if normalized_table == normalized_factory:
                    workbook.close()
                    return (sheet_name, table_name)
                
                # Substring match (factory in table or table in factory)
                if normalized_factory in normalized_table or normalized_table in normalized_factory:
                    workbook.close()
                    return (sheet_name, table_name)
            
            # Strategy 4: Substring match with cleaned versions
            if factory_cleaned in table_cleaned or table_cleaned in factory_cleaned:
                workbook.close()
                return (sheet_name, table_name)
            
            # Strategy 5: Case-insensitive comparison (though Persian doesn't have case)
            if table_cleaned.lower() == factory_cleaned.lower():
                workbook.close()
                return (sheet_name, table_name)
    
    # If no match found, print debug information before closing
    print(f"  [DEBUG] Available tables in file:")
    for sheet_name in available_sheets:
        worksheet = workbook[sheet_name]
        if worksheet.tables:
            for table_name in worksheet.tables.keys():
                print(f"    - Sheet '{sheet_name}', Table '{table_name}' (repr: {repr(table_name)})")
        else:
            print(f"    - Sheet '{sheet_name}': No tables found")
    print(f"  [DEBUG] Looking for factory name: '{factory_name}' (repr: {repr(factory_name)})")
    
    # Close workbook
    workbook.close()
    
    return None


def normalize_dataframe_columns(df: pd.DataFrame, expected_columns: List[str]) -> pd.DataFrame:
    """
    Normalize column names and map to expected columns.
    
    Args:
        df: DataFrame with potentially unnormalized column names
        expected_columns: List of expected column names
        
    Returns:
        DataFrame with normalized and mapped column names
    """
    # Normalize column names
    column_mapping = {}
    for col in df.columns:
        normalized = unicodedata.normalize('NFC', str(col).strip())
        column_mapping[col] = normalized
    
    df = df.rename(columns=column_mapping)
    
    # Map to expected columns
    for expected_col in expected_columns:
        if expected_col not in df.columns:
            for actual_col in df.columns:
                if unicodedata.normalize('NFC', actual_col.strip()) == unicodedata.normalize('NFC', expected_col.strip()):
                    df = df.rename(columns={actual_col: expected_col})
                    break
    
    return df


def validate_dataframe_columns(df: pd.DataFrame, expected_columns: List[str]) -> None:
    """
    Validate that DataFrame contains all expected columns.
    
    Args:
        df: DataFrame to validate
        expected_columns: List of expected column names
        
    Raises:
        ValueError: If required columns are missing
    """
    missing_columns = [col for col in expected_columns if col not in df.columns]
    
    if missing_columns:
        print(f"\n[ERROR] Missing expected columns ({len(missing_columns)}):")
        for col in missing_columns:
            print(f"  - '{col}'")
        print("\n[INFO] Available columns:")
        for col in df.columns:
            print(f"  - '{col}'")
        raise ValueError(f"Missing {len(missing_columns)} expected column(s). See output above.")


def validate_dataframe_has_data(df: pd.DataFrame, data_columns: List[str]) -> None:
    """
    Validate that DataFrame has non-null data.
    
    Args:
        df: DataFrame to validate
        data_columns: List of data column names to check
        
    Raises:
        ValueError: If DataFrame is empty or has no data
    """
    if df.empty:
        raise ValueError("DataFrame is empty after loading Excel files.")
    
    if data_columns:
        non_null_count = df[data_columns].notna().any(axis=1).sum()
        if non_null_count == 0:
            raise ValueError("No data rows found in DataFrame. All values are null/empty.")


def filter_empty_rows(df: pd.DataFrame, data_columns: List[str]) -> pd.DataFrame:
    """
    Filter out rows where all data columns are null/empty.
    
    Args:
        df: DataFrame to filter
        data_columns: List of data column names to check
        
    Returns:
        Filtered DataFrame
    """
    if not data_columns:
        return df
    
    has_data_mask = df[data_columns].notna().any(axis=1)
    for col in data_columns:
        has_data_mask = has_data_mask | (df[col].astype(str).str.strip() != '')
    
    return df[has_data_mask].copy()


def safe_get_column(row: pd.Series, column_name: str, default=None):
    """
    Safely get a column value from a pandas Series, handling missing columns and NaN values.
    
    Args:
        row: pandas Series (DataFrame row)
        column_name: Column name to access
        default: Default value if column is missing or NaN
        
    Returns:
        Column value or default
    """
    if column_name not in row.index:
        return default
    value = row[column_name]
    if pd.isna(value):
        return default
    return value


def transform_distributor_delivery_row(
    row: pd.Series,
    batch_id: int,
    persian_columns: List[str]
) -> tuple:
    """
    Transform a single DataFrame row to staging tuple for distributor deliveries.
    
    Args:
        row: DataFrame row with Persian column names
        batch_id: Batch ID for the row
        persian_columns: List of Persian column names (for validation)
        
    Returns:
        Tuple ready for insertion into staging table
    """
    request_date = parse_excel_date(safe_get_column(row, 'تاریخ درخواست'))
    expiry_date = parse_excel_date(safe_get_column(row, 'تاریخ انقضاء'))
    release_date = parse_excel_date(safe_get_column(row, 'تاریخ ریلیز'))
    delivery_date = parse_excel_date(safe_get_column(row, 'تاریخ تحویل'))
    
    delivered_qty = safe_int(safe_get_column(row, 'تعداد تحویلی'))
    delivered_qty_round_up = safe_int(safe_get_column(row, 'تعداد تحویلی رند بالا'))
    delivered_qty_round_down = safe_int(safe_get_column(row, 'تعداد تحویلی رند پایین'))
    warehouse_exit_qty = safe_int(safe_get_column(row, 'تعداد خروج از انبار'))
    routine_delivery_qty = safe_int(safe_get_column(row, 'تعداد تحویل روتین'))
    supply_chain_request_qty = safe_int(safe_get_column(row, 'تعداد درخواست زنجیره تامین'))
    days_between_delivery_release = safe_int(safe_get_column(row, 'تعداد روز بین تاریخ تحویلی و ریلیز'))
    
    month = safe_get_column(row, 'ماه')
    if month is not None:
        try:
            month = int(month)
        except:
            month = None
    
    source_file = safe_get_column(row, 'source_file', '')
    
    def safe_str(val, default=''):
        if val is None or pd.isna(val):
            return default
        return str(val)
    
    return (
        batch_id,
        safe_str(safe_get_column(row, 'کد دارو')),
        safe_str(safe_get_column(row, 'کالا')),
        safe_str(safe_get_column(row, 'نام پخش')),
        safe_str(safe_get_column(row, 'شماره بچ')),
        expiry_date,
        delivered_qty,
        delivered_qty_round_up,
        delivered_qty_round_down,
        request_date,
        delivery_date,
        month,
        safe_str(safe_get_column(row, 'شماره نامه خروج از انبار')),
        warehouse_exit_qty,
        safe_str(safe_get_column(row, 'جزئیات خروج از انبار')),
        safe_str(safe_get_column(row, 'وضعیت رسید')),
        release_date,
        days_between_delivery_release,
        routine_delivery_qty,
        supply_chain_request_qty,
        safe_str(safe_get_column(row, 'کارخانه')),
        None,  # company_name
        safe_str(safe_get_column(row, 'توضیحات')),
        source_file,
        None,  # row_hash - no longer needed for deduplication
    )


def load_excel_files_from_dropbox(
    dropbox_client: DropboxClient,
    shared_link: str,
    file_pattern: str,
    expected_files: List[str],
    ignored_files: List[str],
    persian_columns: List[str],
    header_row: int = 7
) -> pd.DataFrame:
    """
    Load and concatenate Excel files from Dropbox, matching factory names to Excel table names.
    
    Args:
        dropbox_client: DropboxClient instance
        shared_link: Dropbox shared link
        file_pattern: Regex pattern to match files
        expected_files: List of expected file names
        ignored_files: List of files to ignore
        persian_columns: List of expected Persian column names
        header_row: Row number (0-indexed) to use as header
        
    Returns:
        Concatenated DataFrame with all data
    """
    print(f"Downloading files from Dropbox shared link: {shared_link}")
    print("Checking for expected files...")
    
    files = dropbox_client.list_files(shared_link=shared_link, pattern=file_pattern)
    
    if not files:
        raise ValueError(f"No files found in Dropbox shared folder matching pattern '{file_pattern}'")
    
    # Check expected files
    if expected_files:
        found_file_names = {file_info['name'] for file_info in files}
        found = [f for f in expected_files if f in found_file_names]
        missing = [f for f in expected_files if f not in found_file_names]
        
        if found:
            print(f"[OK] Found {len(found)} expected file(s):")
            for filename in found:
                print(f"  - {filename}")
        
        if missing:
            print(f"[WARN] Missing {len(missing)} expected file(s):")
            for filename in missing:
                print(f"  - {filename}")
    
    # Filter ignored files
    files_to_process = [f for f in files if f['name'] not in (ignored_files or [])]
    
    if not files_to_process:
        raise ValueError("No files to process after filtering ignored files")
    
    # Process each file
    dataframes = []
    skipped_files = []
    
    for file_info in files_to_process:
        file_name = file_info['name']
        
        try:
            factory_name = extract_factory_name_from_filename(file_name)
            if not factory_name:
                print(f"[WARN] Could not extract factory name from filename: {file_name}. Skipping.")
                skipped_files.append(file_name)
                continue
            
            print(f"\n[INFO] Processing file: {file_name}")
            print(f"  Extracted factory name: {factory_name}")
            
            file_shared_link = file_info.get('_shared_link') if file_info.get('_is_shared') else shared_link
            matching_table = find_matching_table(dropbox_client, file_info, factory_name, file_shared_link)
            
            if not matching_table:
                print(f"  [ERROR] No table found matching factory name '{factory_name}'")
                skipped_files.append(file_name)
                continue
            
            sheet_name, table_name = matching_table
            print(f"  Using table: '{table_name}' in sheet: '{sheet_name}'")
            
            df = dropbox_client.read_excel_table(
                file_info['path'],
                sheet_name=sheet_name,
                table_name=table_name,
                shared_link=file_shared_link,
                file_name=file_name
            )
            
            if df.empty or len(df) == 0:
                print(f"  [WARN] Table '{table_name}' has no data rows. Skipping.")
                skipped_files.append(file_name)
                continue
            
            df['source_file'] = file_name
            dataframes.append(df)
            print(f"  [OK] Successfully loaded {len(df)} rows from table '{table_name}'")
            
        except ValueError as e:
            error_msg = str(e)
            if "not found" in error_msg.lower() and ("table" in error_msg.lower() or "sheet" in error_msg.lower()):
                print(f"  [ERROR] {error_msg}")
            elif "only" in error_msg and "lines in file" in error_msg:
                print(f"  [WARN] {error_msg}. Skipping.")
            else:
                print(f"  [ERROR] {error_msg}")
            skipped_files.append(file_name)
        except Exception as e:
            print(f"  [ERROR] Failed to process file '{file_name}': {str(e)}")
            skipped_files.append(file_name)
    
    if not dataframes:
        raise ValueError(
            f"No valid Excel files could be loaded. "
            f"Total files found: {len(files)}, Skipped: {len(skipped_files)}"
        )
    
    # Filter out empty DataFrames before concatenation to avoid FutureWarning
    # about concatenation with empty or all-NA entries
    non_empty_dataframes = [df for df in dataframes if not df.empty and len(df) > 0]
    
    if not non_empty_dataframes:
        raise ValueError(
            f"No valid data found in Excel files. "
            f"Total files found: {len(files)}, Skipped: {len(skipped_files)}"
        )
    
    print(f"\n[INFO] Concatenating {len(non_empty_dataframes)} file(s)...")
    # Use sort=False to avoid FutureWarning about dtype inference
    df = pd.concat(non_empty_dataframes, ignore_index=True, sort=False)
    
    if skipped_files:
        print(f"[INFO] Summary: Loaded {len(non_empty_dataframes)} file(s), Skipped {len(skipped_files)} file(s)")
    
    # Normalize and validate
    df = normalize_dataframe_columns(df, persian_columns)
    validate_dataframe_columns(df, persian_columns)
    validate_dataframe_has_data(df, persian_columns)
    df = filter_empty_rows(df, persian_columns)
    
    # Filter to only include expected columns (plus source_file if present)
    # This ensures we don't have extra columns from hidden columns or other sources
    # Extra columns won't cause errors, but filtering keeps the DataFrame clean
    columns_to_keep = persian_columns.copy()
    if 'source_file' in df.columns:
        columns_to_keep.append('source_file')
    df = df[columns_to_keep]
    
    loaded_files = df['source_file'].unique().tolist() if 'source_file' in df.columns else []
    print(f"\n✓ Successfully loaded {len(df)} rows from {len(loaded_files)} file(s):")
    for filename in sorted(loaded_files):
        file_rows = len(df[df['source_file'] == filename])
        print(f"  - {filename} ({file_rows} rows)")
    
    return df


def transform_dataframe_to_staging_rows(
    df: pd.DataFrame,
    batch_id: int,
    persian_columns: List[str]
) -> List[tuple]:
    """
    Transform DataFrame rows to staging table tuples.
    
    Args:
        df: DataFrame with Persian column names
        batch_id: Batch ID for the rows
        persian_columns: List of Persian column names
        
    Returns:
        List of tuples ready for insertion into staging table
    """
    missing_cols = [col for col in persian_columns if col not in df.columns]
    if missing_cols:
        raise ValueError(f"Missing required columns in DataFrame: {missing_cols}")
    
    staging_rows = []
    total_rows = len(df)
    progress_interval = max(1000, total_rows // 10)
    
    for idx, (_, row) in enumerate(df.iterrows(), 1):
        if idx % progress_interval == 0 or idx == total_rows:
            print(f"  Transforming row {idx}/{total_rows} ({idx*100//total_rows}%)...", end='\r', flush=True)
        
        staging_row = transform_distributor_delivery_row(row, batch_id, persian_columns)
        staging_rows.append(staging_row)
    
    print(" " * 60, end='\r', flush=True)
    
    return staging_rows

