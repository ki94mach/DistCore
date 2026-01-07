"""Staging table utility functions for deduplication and incremental loading."""

import hashlib
from datetime import date
from typing import List, Optional, Any
import pandas as pd

from ..services.sql_server_db.factory import DBConnectionFactory


def calculate_row_hash(values: List[Any]) -> bytes:
    """
    Calculate SHA-256 hash of a list of values for row deduplication.
    
    NULL/NaN values are normalized to empty string for consistent hashing.
    
    Args:
        values: List of values to hash (all data columns excluding metadata)
        
    Returns:
        SHA-256 hash as bytes (32 bytes)
        
    Example:
        >>> hash1 = calculate_row_hash(['Product A', 'Distributor B', 100, '2024-01-15'])
        >>> hash2 = calculate_row_hash(['Product A', 'Distributor B', 100, '2024-01-15'])
        >>> hash1 == hash2
        True
    """
    def normalize_value(val):
        """Normalize value for hashing: convert None/NaN to empty string, otherwise convert to string."""
        if pd.isna(val) if isinstance(val, (float, type(pd.NA))) else (val is None):
            return ''
        return str(val)
    
    # Normalize all values and join with delimiter
    normalized_values = [normalize_value(val) for val in values]
    hash_string = '|'.join(normalized_values)
    return hashlib.sha256(hash_string.encode('utf-8')).digest()


def check_row_hash_exists(
    staging_table: str,
    row_hash: bytes,
    cursor
) -> bool:
    """
    Check if a row_hash already exists in the staging table.
    
    Args:
        staging_table: Name of the staging table (e.g., '[Data].[stg_DistributorDeliveries]')
        row_hash: SHA-256 hash bytes to check
        cursor: Database cursor (already connected)
        
    Returns:
        True if row_hash exists, False otherwise
        
    Example:
        >>> with conn.cursor() as cursor:
        ...     exists = check_row_hash_exists('[Data].[stg_DistributorDeliveries]', hash_bytes, cursor)
    """
    cursor.execute(f"""
        SELECT 1 
        FROM {staging_table}
        WHERE row_hash = ?
    """, row_hash)
    return cursor.fetchone() is not None


def get_last_successful_ingestion_date(
    batch_type: str,
    connection_factory: DBConnectionFactory,
    database_type: str = 'test'
) -> Optional[date]:
    """
    Get the date of the last successful batch ingestion for a given batch type.
    
    Args:
        batch_type: Batch type identifier (e.g., 'DISTRIBUTOR_DELIVERIES')
        connection_factory: Database connection factory
        database_type: Database type ('source' or 'test')
        
    Returns:
        Date of last successful ingestion, or None if no successful batches exist
        
    Example:
        >>> factory = DBConnectionFactory()
        >>> last_date = get_last_successful_ingestion_date('DISTRIBUTOR_DELIVERIES', factory)
        >>> if last_date:
        ...     print(f"Last ingestion: {last_date}")
    """
    with connection_factory.connection(database_type) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT MAX(CAST(br.finished_at AS DATE))
            FROM [Data].[ctl_BatchRun] br
            WHERE br.batch_type = ?
              AND br.status = 'SUCCESS'
              AND br.finished_at IS NOT NULL
        """, batch_type)
        result = cursor.fetchone()
        return result[0] if result and result[0] is not None else None

