"""SQL query manipulation utilities for pipelines."""

import re
from datetime import date
from typing import Optional


def parse_select_statement(query: str) -> str:
    """
    Extract the SELECT statement from a SQL query, skipping DECLARE and comments.
    
    This is useful when SQL files contain DECLARE statements and comments that
    need to be removed before execution.
    
    Args:
        query: Full SQL query content (may include DECLARE, comments, etc.)
        
    Returns:
        SELECT statement only (with comments and DECLARE removed)
        
    Example:
        >>> sql = '''
        ... DECLARE @since DATE = '2024-01-01';
        ... -- This is a comment
        ... SELECT * FROM table WHERE date >= @since
        ... '''
        >>> parse_select_statement(sql)
        'SELECT * FROM table WHERE date >= @since'
    """
    lines = query.split('\n')
    select_lines = []
    in_select = False
    
    for line in lines:
        stripped = line.strip().upper()
        # Skip DECLARE statements and comments
        if stripped.startswith(('DECLARE', '--', '/*')):
            continue
        if stripped.startswith('SELECT'):
            in_select = True
        if in_select:
            select_lines.append(line)
    
    return '\n'.join(select_lines)


def substitute_date_parameter(query: str, parameter_name: str, since_date: Optional[date]) -> str:
    """
    Replace a date parameter placeholder in SQL query with actual date value or NULL.
    
    Args:
        query: SQL query with parameter placeholder (e.g., @since)
        parameter_name: Name of the parameter to substitute (without @ prefix)
        since_date: Date to substitute, or None to substitute NULL
        
    Returns:
        Query with date parameter substituted
        
    Example:
        >>> query = "SELECT * FROM table WHERE date >= @since"
        >>> substitute_date_parameter(query, 'since', date(2024, 1, 1))
        "SELECT * FROM table WHERE date >= '2024-01-01'"
        >>> substitute_date_parameter(query, 'since', None)
        "SELECT * FROM table WHERE date >= NULL"
    """
    if since_date:
        date_str = since_date.strftime("'%Y-%m-%d'")
        return query.replace(f'@{parameter_name}', date_str)
    return query.replace(f'@{parameter_name}', 'NULL')


def apply_date_equality_filter(
    query: str,
    date_column: str,
    date_value: date
) -> str:
    """
    Replace a range filter (>=) with an equality filter (=) for a specific date column.
    
    This is useful when you want to change from "load all data since date" to
    "load only data for this specific date".
    
    Args:
        query: SQL query with range filter pattern
        date_column: Name of the date column (e.g., '[FKDate]')
        date_value: Date value to use in equality filter
        
    Returns:
        Query with equality filter applied
        
    Example:
        >>> query = "SELECT * FROM table WHERE ('2024-01-01' IS NULL OR [FKDate] >= '2024-01-01')"
        >>> apply_date_equality_filter(query, '[FKDate]', date(2024, 1, 1))
        "SELECT * FROM table WHERE AND [FKDate] = '2024-01-01'"
    """
    date_str = date_value.strftime("'%Y-%m-%d'")
    
    # Pattern matches: (date_str IS NULL OR column >= date_str)
    # with various whitespace possibilities
    pattern = (
        r'\(\s*' + re.escape(date_str) +
        r'\s+IS\s+NULL\s+OR\s+' + re.escape(date_column) +
        r'\s+>=\s+' + re.escape(date_str) + r'\s*\)'
    )
    replacement = f"AND {date_column} = {date_str}"
    
    return re.sub(pattern, replacement, query, flags=re.IGNORECASE)

