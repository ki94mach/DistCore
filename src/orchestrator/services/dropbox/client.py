"""Dropbox client for downloading and reading files."""

import io
import re
from pathlib import Path
from typing import List, Optional, Dict, Any, Tuple
import pandas as pd

try:
    import dropbox
    from dropbox.exceptions import ApiError, AuthError
except ImportError:
    raise ImportError(
        "dropbox package is required. Install it with: pip install dropbox"
    )

from .config import DropboxConfigLoader


def _is_shared_link(path_or_link: str) -> bool:
    """
    Check if the input is a Dropbox shared link.
    
    Args:
        path_or_link: Path or shared link string
        
    Returns:
        True if it's a shared link, False otherwise
    """
    return path_or_link.startswith('https://www.dropbox.com/') or path_or_link.startswith('https://dropbox.com/')


def _normalize_shared_link(shared_link: str) -> str:
    """
    Normalize a Dropbox shared link URL.
    
    Removes query parameters like ?dl=0 or ?dl=1 and ensures consistent format.
    
    Args:
        shared_link: Dropbox shared link URL
        
    Returns:
        Normalized shared link URL
    """
    # Remove query parameters
    if '?' in shared_link:
        shared_link = shared_link.split('?')[0]
    
    # Ensure it ends with the proper format
    return shared_link


class DropboxClient:
    """Client for interacting with Dropbox API."""
    
    def __init__(self, access_token: Optional[str] = None, config_loader: Optional[DropboxConfigLoader] = None):
        """
        Initialize the Dropbox client.
        
        Args:
            access_token: Optional Dropbox access token
            config_loader: Optional config loader instance
        """
        if config_loader is None:
            config_loader = DropboxConfigLoader(access_token=access_token)
        
        self._config_loader = config_loader
        config = config_loader.load_config()
        self._access_token = config['access_token']
        self._auth_method = config.get('auth_method', 'access_token')
        self._dbx = dropbox.Dropbox(self._access_token)
        
        # Store refresh info for OAuth refresh method
        if self._auth_method == 'oauth_refresh':
            self._refresh_token = config.get('refresh_token')
            self._app_key = config.get('app_key')
            self._app_secret = config.get('app_secret')
        else:
            self._refresh_token = None
            self._app_key = None
            self._app_secret = None
    
    def _refresh_and_retry(self) -> None:
        """Refresh the access token and update the Dropbox client."""
        if not all([self._app_key, self._app_secret, self._refresh_token]):
            raise ValueError("Cannot refresh token: missing app_key, app_secret, or refresh_token")
        
        # Use the config loader's refresh method
        self._access_token = self._config_loader._refresh_access_token(
            self._app_key, self._app_secret, self._refresh_token
        )
        self._dbx = dropbox.Dropbox(self._access_token)
    
    def list_files(self, folder_path: str, pattern: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        List files in a Dropbox folder or shared link.
        
        Args:
            folder_path: Path to the folder in Dropbox (e.g., '/Data/Deliveries') 
                        or a shared link URL (e.g., 'https://www.dropbox.com/s/...')
            pattern: Optional regex pattern to filter file names
            
        Returns:
            List of dictionaries containing file metadata (name, path, size, etc.)
        """
        try:
            files = []
            is_shared_link = _is_shared_link(folder_path)
            
            if is_shared_link:
                # Use shared link - create SharedLink object from URL
                normalized_link = _normalize_shared_link(folder_path)
                shared_link_obj = dropbox.files.SharedLink(url=normalized_link)
                result = self._dbx.files_list_folder('', shared_link=shared_link_obj)
            else:
                # Use regular folder path
                result = self._dbx.files_list_folder(folder_path)
            
            while True:
                for entry in result.entries:
                    if isinstance(entry, dropbox.files.FileMetadata):
                        file_name = entry.name
                        if pattern is None or re.search(pattern, file_name):
                            # For shared links, path_display might be relative
                            # Store both the relative path and the shared link context
                            file_path = entry.path_display
                            if is_shared_link:
                                # Store the shared link for later use when downloading
                                files.append({
                                    'name': file_name,
                                    'path': file_path,
                                    'size': entry.size,
                                    'modified': entry.server_modified,
                                    '_shared_link': normalized_link,
                                    '_is_shared': True,
                                })
                            else:
                                files.append({
                                    'name': file_name,
                                    'path': file_path,
                                    'size': entry.size,
                                    'modified': entry.server_modified,
                                })
                
                if not result.has_more:
                    break
                result = self._dbx.files_list_folder_continue(result.cursor)
            
            return files
        except AuthError as e:
            # Try to refresh token if using OAuth refresh method
            if self._auth_method == 'oauth_refresh' and self._refresh_token:
                try:
                    self._refresh_and_retry()
                    # Retry the operation
                    is_shared_link = _is_shared_link(folder_path)
                    if is_shared_link:
                        normalized_link = _normalize_shared_link(folder_path)
                        shared_link_obj = dropbox.files.SharedLink(url=normalized_link)
                        result = self._dbx.files_list_folder('', shared_link=shared_link_obj)
                    else:
                        result = self._dbx.files_list_folder(folder_path)
                    
                    # Process the result
                    files = []
                    while True:
                        for entry in result.entries:
                            if isinstance(entry, dropbox.files.FileMetadata):
                                file_name = entry.name
                                if pattern is None or re.search(pattern, file_name):
                                    file_path = entry.path_display
                                    if is_shared_link:
                                        files.append({
                                            'name': file_name,
                                            'path': file_path,
                                            'size': entry.size,
                                            'modified': entry.server_modified,
                                            '_shared_link': normalized_link,
                                            '_is_shared': True,
                                        })
                                    else:
                                        files.append({
                                            'name': file_name,
                                            'path': file_path,
                                            'size': entry.size,
                                            'modified': entry.server_modified,
                                        })
                        if not result.has_more:
                            break
                        result = self._dbx.files_list_folder_continue(result.cursor)
                    return files
                except Exception:
                    pass  # If refresh fails, fall through to error message
            
            error_msg = (
                f"Dropbox authentication failed: {str(e)}\n"
                "This usually means your access token is invalid or expired.\n"
            )
            if self._auth_method == 'oauth_refresh':
                error_msg += "Token refresh was attempted but failed. Please check your refresh token configuration."
            else:
                error_msg += "Please verify your access token or re-authorize the application."
            raise Exception(error_msg) from e
        except ApiError as e:
            raise Exception(f"Failed to list files in Dropbox folder '{folder_path}': {str(e)}")
    
    def download_file(self, file_path: str, shared_link: Optional[str] = None) -> bytes:
        """
        Download a file from Dropbox.
        
        Args:
            file_path: Path to the file in Dropbox (relative path if using shared_link)
            shared_link: Optional shared link URL if the file is from a shared folder
            
        Returns:
            File contents as bytes
        """
        try:
            if shared_link:
                normalized_link = _normalize_shared_link(shared_link)
                shared_link_obj = dropbox.files.SharedLink(url=normalized_link)
                _, response = self._dbx.files_download(file_path, shared_link=shared_link_obj)
            else:
                _, response = self._dbx.files_download(file_path)
            return response.content
        except AuthError as e:
            # Try to refresh token if using OAuth refresh method
            if self._auth_method == 'oauth_refresh' and self._refresh_token:
                try:
                    self._refresh_and_retry()
                    # Retry the operation
                    if shared_link:
                        normalized_link = _normalize_shared_link(shared_link)
                        shared_link_obj = dropbox.files.SharedLink(url=normalized_link)
                        _, response = self._dbx.files_download(file_path, shared_link=shared_link_obj)
                    else:
                        _, response = self._dbx.files_download(file_path)
                    return response.content
                except Exception:
                    pass  # If refresh fails, fall through to error message
            
            error_msg = (
                f"Dropbox authentication failed: {str(e)}\n"
                "This usually means your access token is invalid or expired.\n"
            )
            if self._auth_method == 'oauth_refresh':
                error_msg += "Token refresh was attempted but failed. Please check your refresh token configuration."
            else:
                error_msg += "Please verify your access token or re-authorize the application."
            raise Exception(error_msg) from e
        except ApiError as e:
            raise Exception(f"Failed to download file '{file_path}' from Dropbox: {str(e)}")
    
    def read_excel_file(
        self,
        file_path: str,
        sheet_name: Optional[str] = None,
        header_row: Optional[int] = None,
        skip_rows: Optional[int] = None,
        shared_link: Optional[str] = None
    ) -> pd.DataFrame:
        """
        Read an Excel file from Dropbox into a pandas DataFrame.
        
        Args:
            file_path: Path to the Excel file in Dropbox (relative path if using shared_link)
            sheet_name: Optional sheet name (defaults to first sheet)
            header_row: Optional row number (0-indexed) to use as column headers.
                       If None, uses default pandas behavior (first row).
                       For files where headers are on row 8, use header_row=7.
            skip_rows: Optional number of rows to skip at the start.
                      If header_row is specified, this is ignored.
                      If None and header_row is None, no rows are skipped.
            shared_link: Optional shared link URL if the file is from a shared folder
            
        Returns:
            pandas DataFrame containing the file data
        """
        file_content = self.download_file(file_path, shared_link=shared_link)
        
        # First, check if the file has enough rows
        if header_row is not None:
            # Read the Excel file to check row count
            try:
                import openpyxl
                workbook = openpyxl.load_workbook(io.BytesIO(file_content), read_only=True)
                
                # If sheet_name is specified, check that sheet; otherwise check first sheet
                if sheet_name:
                    if sheet_name not in workbook.sheetnames:
                        raise ValueError(f"Sheet '{sheet_name}' not found in file")
                    ws = workbook[sheet_name]
                else:
                    ws = workbook.active
                
                # Check if there are enough rows (header_row + at least 1 data row)
                max_row = ws.max_row
                if max_row <= header_row:
                    raise ValueError(
                        f"File has only {max_row} rows, but header_row={header_row} requires at least {header_row + 1} rows. "
                        f"Sheet: {ws.title if hasattr(ws, 'title') else 'unknown'}"
                    )
                
                workbook.close()
            except ImportError:
                # openpyxl not available, skip the check
                pass
            except Exception as e:
                # If check fails, still try to read - let pandas handle the error
                pass
        
        read_kwargs = {
            'io': io.BytesIO(file_content),
            'sheet_name': sheet_name,
            'engine': 'openpyxl'
        }
        
        if header_row is not None:
            # Use specified row as header (0-indexed)
            # pandas will automatically skip rows before the header
            read_kwargs['header'] = header_row
        elif skip_rows is not None:
            # Skip specified number of rows
            read_kwargs['skiprows'] = range(skip_rows)
        
        return pd.read_excel(**read_kwargs)
    
    def read_csv_file(self, file_path: str, encoding: str = 'utf-8', shared_link: Optional[str] = None) -> pd.DataFrame:
        """
        Read a CSV file from Dropbox into a pandas DataFrame.
        
        Args:
            file_path: Path to the CSV file in Dropbox (relative path if using shared_link)
            encoding: File encoding (default: utf-8)
            shared_link: Optional shared link URL if the file is from a shared folder
            
        Returns:
            pandas DataFrame containing the file data
        """
        file_content = self.download_file(file_path, shared_link=shared_link)
        return pd.read_csv(io.BytesIO(file_content), encoding=encoding)
    
    def concatenate_excel_files(
        self,
        folder_path: str,
        file_pattern: Optional[str] = None,
        sheet_name: Optional[str] = None,
        header_row: Optional[int] = None,
        skip_rows: Optional[int] = None,
        add_source_file_column: bool = True
    ) -> pd.DataFrame:
        """
        Download and concatenate multiple Excel files from a Dropbox folder or shared link.
        
        Args:
            folder_path: Path to the folder containing Excel files (e.g., '/Data/Deliveries')
                        or a shared link URL (e.g., 'https://www.dropbox.com/s/...')
            file_pattern: Optional regex pattern to filter file names
            sheet_name: Optional sheet name (defaults to first sheet)
            header_row: Optional row number (0-indexed) to use as column headers.
                       For files where headers are on row 8, use header_row=7.
            skip_rows: Optional number of rows to skip at the start.
                      If header_row is specified, this is ignored.
            add_source_file_column: If True, add a column with the source file name
            
        Returns:
            Concatenated pandas DataFrame
        """
        files = self.list_files(folder_path, pattern=file_pattern)
        
        if not files:
            raise ValueError(f"No files found in Dropbox folder '{folder_path}' matching pattern '{file_pattern}'")
        
        dataframes = []
        skipped_files = []
        
        for file_info in files:
            try:
                # Check if this file is from a shared link
                shared_link = file_info.get('_shared_link') if file_info.get('_is_shared') else None
                
                df = self.read_excel_file(
                    file_info['path'],
                    sheet_name=sheet_name,
                    header_row=header_row,
                    skip_rows=skip_rows,
                    shared_link=shared_link
                )
                
                # Check if DataFrame is empty or has no data rows
                if df.empty or len(df) == 0:
                    print(f"Warning: File '{file_info['name']}' has no data rows. Skipping.")
                    skipped_files.append(file_info['name'])
                    continue
                
                if add_source_file_column:
                    df['source_file'] = file_info['name']
                
                dataframes.append(df)
            except ValueError as e:
                # Handle specific error about insufficient rows
                error_msg = str(e)
                if "only" in error_msg and "lines in file" in error_msg:
                    print(f"Warning: File '{file_info['name']}' has insufficient rows for header_row={header_row}. Skipping.")
                    print(f"  Error: {error_msg}")
                    skipped_files.append(file_info['name'])
                    continue
                else:
                    # Re-raise if it's a different ValueError
                    raise
            except Exception as e:
                # For other errors, log and skip the file
                print(f"Warning: Failed to read file '{file_info['name']}' from Dropbox: {str(e)}")
                print(f"  Skipping this file and continuing with others...")
                skipped_files.append(file_info['name'])
                continue
        
        if not dataframes:
            error_msg = f"No valid data could be read from any files in '{folder_path}'"
            if skipped_files:
                error_msg += f"\nSkipped files: {', '.join(skipped_files)}"
            raise ValueError(error_msg)
        
        if skipped_files:
            print(f"\nNote: Successfully processed {len(dataframes)} file(s), skipped {len(skipped_files)} file(s)")
        
        return pd.concat(dataframes, ignore_index=True)
    
    def test_connection(self) -> bool:
        """
        Test the Dropbox connection.
        
        Returns:
            True if connection is successful
            
        Raises:
            Exception: If connection fails
        """
        try:
            self._dbx.users_get_current_account()
            return True
        except AuthError as e:
            raise Exception(f"Dropbox authentication failed: {str(e)}")
        except Exception as e:
            raise Exception(f"Dropbox connection test failed: {str(e)}")

