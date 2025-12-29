"""Result set formatting utilities."""

import pyodbc
from typing import List, Dict, Any, Optional


def format_result_set(cursor: pyodbc.Cursor) -> Optional[List[Dict[str, Any]]]:
    """
    Format cursor result set as list of dictionaries.
    
    Args:
        cursor: pyodbc cursor with executed query
        
    Returns:
        List of dictionaries (one per row) or None if no result set
        
    Example:
        >>> cursor.execute("SELECT id, name FROM table")
        >>> format_result_set(cursor)
        [{'id': 1, 'name': 'test'}, {'id': 2, 'name': 'test2'}]
    """
    try:
        rows = cursor.fetchall()
        if not rows or not cursor.description:
            return None
        
        columns = [column[0] for column in cursor.description]
        return [dict(zip(columns, row)) for row in rows]
    except pyodbc.ProgrammingError:
        # No result set available
        return None


def format_output_parameters(
    cursor: pyodbc.Cursor,
    output_param_names: List[str]
) -> Dict[str, Any]:
    """
    Format output parameters from cursor result set.
    
    Args:
        cursor: pyodbc cursor with executed query
        output_param_names: List of output parameter names to extract
        
    Returns:
        Dictionary mapping parameter names to values
    """
    try:
        rows = cursor.fetchall()
        if not rows or not cursor.description:
            return {}
        
        columns = [column[0] for column in cursor.description]
        if rows:
            output_row = dict(zip(columns, rows[0]))
            return {name: output_row.get(name) for name in output_param_names}
        return {}
    except pyodbc.ProgrammingError:
        return {}


def format_all_result_sets(cursor: pyodbc.Cursor) -> List[List[Dict[str, Any]]]:
    """
    Format all result sets from cursor.
    
    Args:
        cursor: pyodbc cursor with executed query
        
    Returns:
        List of result sets (each is a list of dictionaries)
    """
    all_results = []
    
    while True:
        try:
            result_set = format_result_set(cursor)
            if result_set:
                all_results.append(result_set)
            
            if not cursor.nextset():
                break
        except (pyodbc.ProgrammingError, pyodbc.Error):
            break
    
    return all_results


def extract_result_set_from_cursor(cursor: pyodbc.Cursor) -> Optional[List[Dict[str, Any]]]:
    """
    Extract and format a single result set from cursor.
    Alias for format_result_set for backward compatibility.
    
    Args:
        cursor: pyodbc cursor
        
    Returns:
        List of dictionaries or None
    """
    return format_result_set(cursor)

