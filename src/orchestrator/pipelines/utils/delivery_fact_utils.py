"""Fact table utility functions for distributor deliveries."""

from typing import Optional

HISTORICAL_SOURCE_FILE_PATTERN = "%1404.xlsx"
CURRENT_SOURCE_FILE_PATTERN = "%1405.xlsx"


def fact_has_historical_data(cursor, fact_table: str) -> bool:
    return count_fact_rows(cursor, fact_table, HISTORICAL_SOURCE_FILE_PATTERN) > 0


def delete_current_year_fact_rows(cursor, fact_table: str) -> int:
    query = f"DELETE FROM {fact_table} WHERE source_file LIKE ?"
    cursor.execute(query, (CURRENT_SOURCE_FILE_PATTERN,))
    return cursor.rowcount


def count_fact_rows(
    cursor,
    fact_table: str,
    source_file_pattern: Optional[str] = None,
) -> int:
    if source_file_pattern:
        query = f"SELECT COUNT(1) FROM {fact_table} WHERE source_file LIKE ?"
        cursor.execute(query, (source_file_pattern,))
    else:
        query = f"SELECT COUNT(1) FROM {fact_table}"
        cursor.execute(query)
    row = cursor.fetchone()
    return int(row[0]) if row else 0
