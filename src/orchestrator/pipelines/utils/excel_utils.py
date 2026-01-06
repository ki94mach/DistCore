"""Excel file parsing utilities for pipelines."""

from datetime import date
from typing import Optional
import pandas as pd


def parse_excel_date(date_value) -> Optional[date]:
    """
    Parse Excel date value to Python date object.
    
    Handles various date formats:
    - Python date objects
    - pandas Timestamp objects
    - Excel date serial numbers (float/int)
    - Date strings
    
    Args:
        date_value: Date value from Excel (could be string, Excel date number, or date object)
        
    Returns:
        Python date object or None if parsing fails
        
    Example:
        >>> parse_excel_date(pd.Timestamp('2024-01-15'))
        datetime.date(2024, 1, 15)
        >>> parse_excel_date(45321)  # Excel serial number
        datetime.date(2024, 1, 15)
    """
    if pd.isna(date_value):
        return None
    
    if isinstance(date_value, date):
        return date_value
    
    if isinstance(date_value, pd.Timestamp):
        return date_value.date()
    
    # Try to parse as Excel date number
    if isinstance(date_value, (int, float)):
        try:
            # Excel dates start from 1900-01-01 (but Excel incorrectly treats 1900 as leap year)
            # So we subtract 2 days to account for this
            excel_epoch = pd.Timestamp('1899-12-30')
            return (excel_epoch + pd.Timedelta(days=int(date_value))).date()
        except (ValueError, OverflowError):
            return None
    
    # Try to parse as string (Persian date or standard date)
    if isinstance(date_value, str):
        date_value = date_value.strip()
        if not date_value:
            return None
        
        # Try standard date formats first
        try:
            return pd.to_datetime(date_value).date()
        except:
            pass
    
    return None


def safe_int(value, default: Optional[int] = None) -> Optional[int]:
    """
    Safely convert value to integer, handling NaN and conversion errors.
    
    Args:
        value: Value to convert to integer
        default: Default value to return if conversion fails (default: None)
        
    Returns:
        Integer value or default if conversion fails
        
    Example:
        >>> safe_int(123.5)
        123
        >>> safe_int('456')
        456
        >>> safe_int(None)
        None
        >>> safe_int('invalid', default=0)
        0
    """
    if pd.isna(value):
        return default
    
    try:
        return int(float(value))
    except (ValueError, TypeError):
        return default


