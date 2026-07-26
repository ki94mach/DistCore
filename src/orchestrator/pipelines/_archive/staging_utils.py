"""Staging table utility functions for distributor deliveries."""

from typing import Optional


HISTORICAL_SOURCE_FILE_PATTERN = '%1404.xlsx'
CURRENT_SOURCE_FILE_PATTERN = '%1405.xlsx'


def staging_has_historical_data(cursor, staging_table: str) -> bool:
    """Return True if staging already contains rows from 1404 historical files."""
    return count_staging_rows(
        cursor,
        staging_table,
        source_file_pattern=HISTORICAL_SOURCE_FILE_PATTERN,
    ) > 0


def delete_current_year_staging_rows(cursor, staging_table: str) -> int:
    """Delete staging rows loaded from 1405 current-year files."""
    query = f"DELETE FROM {staging_table} WHERE source_file LIKE ?"
    cursor.execute(query, (CURRENT_SOURCE_FILE_PATTERN,))
    return cursor.rowcount


def sync_all_staging_batch_ids(cursor, staging_table: str, batch_id: int) -> int:
    """Set batch_id on all staging rows so publish includes historical and current data."""
    query = f"UPDATE {staging_table} SET batch_id = ?"
    cursor.execute(query, (batch_id,))
    return cursor.rowcount


def count_staging_rows(cursor, staging_table: str, source_file_pattern: Optional[str] = None) -> int:
    if source_file_pattern:
        query = f"SELECT COUNT(1) FROM {staging_table} WHERE source_file LIKE ?"
        cursor.execute(query, (source_file_pattern,))
    else:
        query = f"SELECT COUNT(1) FROM {staging_table}"
        cursor.execute(query)
    row = cursor.fetchone()
    return int(row[0]) if row else 0
