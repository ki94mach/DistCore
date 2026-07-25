"""Fact table utility functions for distributor deliveries."""

from datetime import date
from typing import Optional

from src.orchestrator.pipelines.utils.date_utils import get_jalali_year


def historical_and_current_years(as_of: Optional[date] = None) -> tuple[str, str]:
    """Return (historical_year, current_year) as Jalali year strings."""
    current = get_jalali_year(as_of or date.today())
    return str(current - 1), str(current)


def source_file_pattern_for_year(year: str) -> str:
    return f"%{year}.xlsx"


def fact_has_historical_data(
    cursor,
    fact_table: str,
    historical_year: Optional[str] = None,
) -> bool:
    year = historical_year or historical_and_current_years()[0]
    return count_fact_rows(cursor, fact_table, source_file_pattern_for_year(year)) > 0


def delete_current_year_fact_rows(
    cursor,
    fact_table: str,
    current_year: Optional[str] = None,
) -> int:
    year = current_year or historical_and_current_years()[1]
    query = f"DELETE FROM {fact_table} WHERE source_file LIKE ?"
    cursor.execute(query, (source_file_pattern_for_year(year),))
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


# Back-compat aliases for callers that still import constants (resolved at import time).
_HISTORICAL_YEAR, _CURRENT_YEAR = historical_and_current_years()
HISTORICAL_SOURCE_FILE_PATTERN = source_file_pattern_for_year(_HISTORICAL_YEAR)
CURRENT_SOURCE_FILE_PATTERN = source_file_pattern_for_year(_CURRENT_YEAR)
