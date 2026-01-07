"""Dropbox client for downloading and reading files from shared links."""

import io
import re
import warnings
import zipfile
from typing import List, Optional, Dict, Any
import pandas as pd
import requests

# Suppress openpyxl warnings about unsupported features - must be before any openpyxl imports
warnings.filterwarnings('ignore', category=UserWarning, module='openpyxl')
warnings.filterwarnings('ignore', message='.*Data Validation.*')
warnings.filterwarnings('ignore', message='.*Print area.*')


def _is_shared_link(path_or_link: str) -> bool:
    """
    Check if the input is a Dropbox shared link.
    
    Args:
        path_or_link: Path or shared link string
        
    Returns:
        True if it's a shared link, False otherwise
    """
    return path_or_link.startswith('https://www.dropbox.com/') or path_or_link.startswith('https://dropbox.com/')


def _normalize_shared_link_for_download(shared_link: str) -> str:
    """
    Normalize a Dropbox shared link URL for direct download.
    
    Args:
        shared_link: Dropbox shared link URL
        
    Returns:
        Normalized shared link URL with dl=1 parameter for direct download
    """
    # Ensure dl=1 parameter is set for direct download
    if 'dl=0' in shared_link:
        return shared_link.replace('dl=0', 'dl=1')
    elif 'dl=1' not in shared_link:
        # Add dl=1 if not present
        separator = '&' if '?' in shared_link else '?'
        return f"{shared_link}{separator}dl=1"
    return shared_link


class DropboxClient:
    """
    Client for downloading files from Dropbox shared links.
    
    This client works without authentication by using public shared links
    and direct HTTP downloads.
    """
    
    def __init__(self, shared_link: Optional[str] = None):
        """
        Initialize the Dropbox client.
        
        Args:
            shared_link: Optional default Dropbox shared link for the folder.
                        Can be overridden per method call.
        """
        self._default_shared_link = shared_link if shared_link else None
    
    def list_files(self, shared_link: Optional[str] = None, pattern: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        List files in a Dropbox shared link folder by downloading and inspecting the ZIP.
        
        Args:
            shared_link: Dropbox shared link URL (e.g., 'https://www.dropbox.com/scl/fo/...')
                        If None, uses the default shared link provided in __init__
            pattern: Optional regex pattern to filter file names
            
        Returns:
            List of dictionaries containing file metadata (name, path, size, etc.)
            
        Raises:
            ValueError: If no shared link is provided
            Exception: If download or extraction fails
        """
        # Use provided shared link or default
        link_to_use = shared_link or self._default_shared_link
        
        if not link_to_use:
            raise ValueError(
                "No shared link provided. Either pass shared_link parameter or "
                "set default shared link in __init__"
            )
        
        if not _is_shared_link(link_to_use):
            raise ValueError(
                f"Invalid shared link format: {link_to_use}. "
                "Expected a Dropbox shared link URL like 'https://www.dropbox.com/scl/fo/...'"
            )
        
        try:
            # Download the folder as ZIP
            download_url = _normalize_shared_link_for_download(link_to_use)
            response = requests.get(download_url, stream=True)
            response.raise_for_status()
            
            # Extract file list from ZIP
            files = []
            with zipfile.ZipFile(io.BytesIO(response.content)) as zip_ref:
                for file_info in zip_ref.filelist:
                    if not file_info.is_dir():
                        file_name = file_info.filename.split('/')[-1]  # Get just the filename
                        
                        # Apply pattern filter if provided
                        if pattern is None or re.search(pattern, file_name):
                            files.append({
                                'name': file_name,
                                'path': file_info.filename,
                                'size': file_info.file_size,
                                'modified': None,  # Not available from ZIP
                                '_shared_link': link_to_use,
                                '_is_shared': True,
                            })
            
            return files
        except requests.exceptions.RequestException as e:
            raise Exception(f"Failed to download from Dropbox shared link: {str(e)}")
        except zipfile.BadZipFile as e:
            raise Exception(f"Failed to extract ZIP from Dropbox shared link: {str(e)}")
    
    def download_file(self, file_path: str, shared_link: Optional[str] = None) -> bytes:
        """
        Download a file from Dropbox using a shared link.
        
        Args:
            file_path: Path to the file within the ZIP (relative path from the shared folder)
            shared_link: Shared link URL. If None, uses the default shared link.
            
        Returns:
            File contents as bytes
            
        Raises:
            ValueError: If no shared link is provided
            Exception: If download fails
        """
        # Use provided shared link or default
        link_to_use = shared_link or self._default_shared_link
        
        if not link_to_use:
            raise ValueError(
                "No shared link provided. Either pass shared_link parameter or "
                "set default shared link in __init__"
            )
        
        try:
            # Download the folder as ZIP
            download_url = _normalize_shared_link_for_download(link_to_use)
            response = requests.get(download_url, stream=True)
            response.raise_for_status()
            
            # Extract the specific file from ZIP
            with zipfile.ZipFile(io.BytesIO(response.content)) as zip_ref:
                # Try to find the file (may have a folder prefix)
                matching_files = [name for name in zip_ref.namelist() if name.endswith(file_path) or name == file_path]
                
                if not matching_files:
                    raise FileNotFoundError(f"File '{file_path}' not found in ZIP archive. Available files: {zip_ref.namelist()[:10]}")
                
                # Use the first matching file
                return zip_ref.read(matching_files[0])
                
        except requests.exceptions.RequestException as e:
            raise Exception(f"Failed to download file '{file_path}' from Dropbox: {str(e)}")
        except zipfile.BadZipFile as e:
            raise Exception(f"Failed to extract file '{file_path}' from ZIP: {str(e)}")
    
    def read_excel_file(
        self,
        file_path: str,
        sheet_name: Optional[str] = None,
        header_row: Optional[int] = None,
        skip_rows: Optional[int] = None,
        shared_link: Optional[str] = None,
        file_name: Optional[str] = None
    ) -> pd.DataFrame:
        """
        Read an Excel file from Dropbox into a pandas DataFrame.
        
        Args:
            file_path: Path to the Excel file in Dropbox (relative path from shared folder)
            sheet_name: Optional sheet name (defaults to first sheet)
            header_row: Optional row number (0-indexed) to use as column headers.
                       If None, uses default pandas behavior (first row).
                       For files where headers are on row 8, use header_row=7.
            skip_rows: Optional number of rows to skip at the start.
                      If header_row is specified, this is ignored.
                      If None and header_row is None, no rows are skipped.
            shared_link: Optional shared link URL if the file is from a shared folder
            file_name: Optional file name for better error messages
            
        Returns:
            pandas DataFrame containing the file data
        """
        file_content = self.download_file(file_path, shared_link=shared_link)
        display_name = file_name or file_path
        
        # First, check if the file has enough rows and sheet exists
        try:
            import openpyxl
            workbook = openpyxl.load_workbook(io.BytesIO(file_content), read_only=True)
            
            # If sheet_name is specified, check that sheet exists
            if sheet_name:
                if sheet_name not in workbook.sheetnames:
                    workbook.close()
                    raise ValueError(
                        f"Worksheet named '{sheet_name}' not found in file '{display_name}'. "
                        f"Available sheets: {', '.join(workbook.sheetnames)}"
                    )
                ws = workbook[sheet_name]
            else:
                ws = workbook.active
            
            # Check if there are enough rows (header_row + at least 1 data row)
            if header_row is not None:
                max_row = ws.max_row
                if max_row <= header_row:
                    workbook.close()
                    raise ValueError(
                        f"File '{display_name}' has only {max_row} rows, but header_row={header_row} requires at least {header_row + 1} rows. "
                        f"Sheet: {ws.title if hasattr(ws, 'title') else 'unknown'}"
                    )
            
            workbook.close()
        except ImportError:
            # openpyxl not available, skip the check
            pass
        except ValueError:
            # Re-raise ValueError (sheet not found, insufficient rows)
            raise
        except Exception:
            # If check fails, still try to read - let pandas handle the error
            pass
        
        read_kwargs = {
            'io': io.BytesIO(file_content),
            'sheet_name': sheet_name,
            'engine': 'openpyxl'
        }
        
        if header_row is not None:
            read_kwargs['header'] = header_row
        elif skip_rows is not None:
            read_kwargs['skiprows'] = skip_rows
        
        try:
            df = pd.read_excel(**read_kwargs)
            
            # Validate that DataFrame has data
            if df.empty:
                raise ValueError(f"File '{display_name}' has no data rows after reading")
            
            return df
        except Exception as e:
            error_msg = str(e)
            if "has only" in error_msg and "lines in file" in error_msg:
                # Enhance the error message
                raise ValueError(
                    f"File '{display_name}' has insufficient rows for header_row={header_row}. {error_msg}"
                )
            raise
    
    def check_expected_files(
        self,
        expected_files: List[str],
        file_pattern: Optional[str] = None,
        shared_link: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Check which expected files are found in the Dropbox shared folder.
        
        Args:
            expected_files: List of expected file names to check for
            file_pattern: Optional regex pattern to filter files (if None, checks all files)
            shared_link: Shared link URL. If None, uses the default shared link.
            
        Returns:
            Dictionary with:
            - 'found': List of expected files that were found
            - 'missing': List of expected files that were not found
            - 'all_found_files': List of all files found (matching pattern if provided)
        """
        all_files = self.list_files(shared_link=shared_link, pattern=file_pattern)
        found_file_names = {file_info['name'] for file_info in all_files}
        
        found = [f for f in expected_files if f in found_file_names]
        missing = [f for f in expected_files if f not in found_file_names]
        all_found_files = [file_info['name'] for file_info in all_files]
        
        return {
            'found': found,
            'missing': missing,
            'all_found_files': all_found_files
        }
    
    def concatenate_excel_files(
        self,
        file_pattern: Optional[str] = None,
        sheet_name: Optional[str] = None,
        header_row: Optional[int] = None,
        skip_rows: Optional[int] = None,
        add_source_file_column: bool = True,
        expected_files: Optional[List[str]] = None,
        ignored_files: Optional[List[str]] = None,
        shared_link: Optional[str] = None
    ) -> pd.DataFrame:
        """
        Download and concatenate multiple Excel files from a Dropbox shared link folder.
        
        Args:
            file_pattern: Optional regex pattern to filter file names
            sheet_name: Optional sheet name (defaults to first sheet)
            header_row: Optional row number (0-indexed) to use as column headers.
                       For files where headers are on row 8, use header_row=7.
            skip_rows: Optional number of rows to skip at the start.
                      If header_row is specified, this is ignored.
            add_source_file_column: If True, add a column with the source file name
            expected_files: Optional list of expected file names to check for (for reporting)
            ignored_files: Optional list of file names to skip/ignore during processing
            shared_link: Shared link URL. If None, uses the default shared link.
            
        Returns:
            Concatenated pandas DataFrame
        """
        # Check expected files if provided
        if expected_files:
            check_result = self.check_expected_files(expected_files, file_pattern, shared_link)
            found_count = len(check_result['found'])
            missing_count = len(check_result['missing'])
            
            if found_count > 0:
                print(f"[OK] Found {found_count} expected file(s):")
                for filename in check_result['found']:
                    print(f"  - {filename}")
            
            if missing_count > 0:
                print(f"[WARN] Missing {missing_count} expected file(s):")
                for filename in check_result['missing']:
                    print(f"  - {filename}")
            
            # Also report any additional files found that match pattern
            additional_files = [f for f in check_result['all_found_files'] if f not in expected_files]
            if additional_files:
                print(f"[INFO] Found {len(additional_files)} additional file(s) matching pattern:")
                for filename in additional_files:
                    print(f"  - {filename}")
        
        files = self.list_files(shared_link=shared_link, pattern=file_pattern)
        
        if not files:
            raise ValueError(f"No files found in Dropbox shared folder matching pattern '{file_pattern}'")
        
        dataframes = []
        skipped_files = []
        
        # Filter out ignored files if provided
        ignored_files_list = ignored_files or []
        
        for file_info in files:
            file_name = file_info['name']
            
            # Skip ignored files
            if file_name in ignored_files_list:
                print(f"[INFO] Ignoring file (in ignore list): {file_name}")
                skipped_files.append(file_name)
                continue
            
            try:
                # Get shared link from file info
                file_shared_link = file_info.get('_shared_link') if file_info.get('_is_shared') else shared_link
                
                df = self.read_excel_file(
                    file_info['path'],
                    sheet_name=sheet_name,
                    header_row=header_row,
                    skip_rows=skip_rows,
                    shared_link=file_shared_link,
                    file_name=file_name
                )
                
                # Check if DataFrame is empty or has no data rows
                if df.empty or len(df) == 0:
                    print(f"[WARN] File '{file_name}' has no data rows. Skipping.")
                    skipped_files.append(file_name)
                    continue
                
                if add_source_file_column:
                    df['source_file'] = file_name
                
                dataframes.append(df)
                print(f"[OK] Successfully loaded: {file_name} ({len(df)} rows)")
                
            except ValueError as e:
                # Handle specific errors
                error_msg = str(e)
                if "only" in error_msg and "lines in file" in error_msg:
                    print(f"[WARN] File '{file_name}' has insufficient rows for header_row={header_row}. Skipping.")
                    print(f"  Error: {error_msg}")
                    skipped_files.append(file_name)
                    continue
                elif "not found" in error_msg.lower() and "sheet" in error_msg.lower():
                    print(f"[ERROR] File '{file_name}' - {error_msg}")
                    print(f"  Available sheets: (checking...)")
                    # Try to list available sheets
                    try:
                        import openpyxl
                        file_shared_link = file_info.get('_shared_link') if file_info.get('_is_shared') else shared_link
                        file_content = self.download_file(file_info['path'], shared_link=file_shared_link)
                        workbook = openpyxl.load_workbook(io.BytesIO(file_content), read_only=True)
                        available_sheets = workbook.sheetnames
                        workbook.close()
                        print(f"  Available sheets in '{file_name}': {', '.join(available_sheets)}")
                    except Exception:
                        pass
                    skipped_files.append(file_name)
                    continue
                else:
                    print(f"[ERROR] File '{file_name}' - {error_msg}")
                    skipped_files.append(file_name)
                    continue
            except Exception as e:
                print(f"[ERROR] Failed to process file '{file_name}': {str(e)}")
                skipped_files.append(file_name)
                continue
        
        if not dataframes:
            raise ValueError(
                f"No valid Excel files could be loaded. "
                f"Total files found: {len(files)}, Skipped: {len(skipped_files)}"
            )
        
        # Concatenate all DataFrames
        result = pd.concat(dataframes, ignore_index=True)
        
        if skipped_files:
            print(f"\n[INFO] Summary: Loaded {len(dataframes)} file(s), Skipped {len(skipped_files)} file(s)")
        
        return result
