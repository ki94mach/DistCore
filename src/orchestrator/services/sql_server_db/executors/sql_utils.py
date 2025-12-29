"""Utility functions for SQL manipulation and parsing."""

import re
from pathlib import Path
from typing import Dict, List, Optional, Union


def clean_parameter_name(param_name: str) -> str:
    """
    Remove @ prefix from parameter name if present.
    
    Args:
        param_name: Parameter name with or without @ prefix
        
    Returns:
        Clean parameter name without @ prefix
        
    Example:
        >>> clean_parameter_name('@batch_id')
        'batch_id'
        >>> clean_parameter_name('batch_id')
        'batch_id'
    """
    return param_name.lstrip('@')


def build_procedure_exec_sql(
    procedure_name: str,
    param_names: List[str]
) -> str:
    """
    Build an EXEC SQL statement for a stored procedure.
    
    Args:
        procedure_name: Full procedure name (e.g., '[Data].[usp_proc]')
        param_names: List of parameter names (without @)
        
    Returns:
        EXEC SQL statement string
        
    Example:
        >>> build_procedure_exec_sql('[Data].[usp_test]', ['param1', 'param2'])
        'EXEC [Data].[usp_test] @param1=?, @param2=?'
    """
    if not param_names:
        return f"EXEC {procedure_name}"
    
    param_list = ", ".join([f"@{name}=?" for name in param_names])
    return f"EXEC {procedure_name} {param_list}"


def build_procedure_exec_with_output_sql(
    procedure_name: str,
    input_param_names: List[str],
    output_param_names: List[str],
    output_variables: Dict[str, str]
) -> str:
    """
    Build an EXEC SQL statement with output parameters.
    
    Args:
        procedure_name: Full procedure name
        input_param_names: List of input parameter names
        output_param_names: List of output parameter names
        output_variables: Dictionary mapping output param names to variable names
        
    Returns:
        EXEC SQL statement with OUTPUT parameters
    """
    exec_params = []
    
    # Add input parameters
    for param_name in input_param_names:
        exec_params.append(f"@{param_name}=?")
    
    # Add output parameters
    for param_name in output_param_names:
        var_name = output_variables[param_name]
        exec_params.append(f"@{param_name}={var_name} OUTPUT")
    
    return f"EXEC {procedure_name} " + ", ".join(exec_params)


def build_output_parameter_declarations(
    output_params: List[str],
    param_type: str = 'BIGINT'
) -> List[str]:
    """
    Build DECLARE statements for output parameter variables.
    
    Args:
        output_params: List of output parameter names (without @)
        param_type: SQL type for the parameters (default: BIGINT)
        
    Returns:
        List of DECLARE statement strings
        
    Example:
        >>> build_output_parameter_declarations(['batch_id'])
        ['DECLARE @batch_id_out BIGINT;']
    """
    declarations = []
    for param_name in output_params:
        var_name = f"@{param_name}_out"
        declarations.append(f"DECLARE {var_name} {param_type};")
    return declarations


def build_output_parameter_select(
    output_variables: Dict[str, str]
) -> str:
    """
    Build SELECT statement to retrieve output parameter values.
    
    Args:
        output_variables: Dictionary mapping param names to variable names
        
    Returns:
        SELECT statement string
        
    Example:
        >>> build_output_parameter_select({'batch_id': '@batch_id_out'})
        'SELECT @batch_id_out AS batch_id'
    """
    selects = [f"{var_name} AS {name}" for name, var_name in output_variables.items()]
    return "SELECT " + ", ".join(selects)


def split_sql_statements(sql_content: str) -> List[str]:
    """
    Split SQL content by GO statements (T-SQL batch separator).
    
    Args:
        sql_content: SQL content to split
        
    Returns:
        List of SQL statements (non-empty, stripped)
        
    Example:
        >>> sql = "SELECT 1; GO SELECT 2;"
        >>> split_sql_statements(sql)
        ['SELECT 1;', 'SELECT 2;']
    """
    statements = re.split(r'\bGO\b', sql_content, flags=re.IGNORECASE)
    return [stmt.strip() for stmt in statements if stmt.strip()]


def substitute_parameters(sql_content: str, parameters: Dict[str, str]) -> str:
    """
    Substitute $(variable_name) placeholders in SQL content.
    
    Args:
        sql_content: SQL content with $(variable) placeholders
        parameters: Dictionary of variable names to values
        
    Returns:
        SQL content with substituted values
        
    Example:
        >>> sql = "SELECT * FROM table WHERE id = $(batch_id)"
        >>> substitute_parameters(sql, {'batch_id': '123'})
        'SELECT * FROM table WHERE id = 123'
    """
    result = sql_content
    for key, value in parameters.items():
        result = result.replace(f"$({key})", str(value))
    return result


def resolve_sql_file_path(
    sql_file_path: Union[str, Path],
    sql_folder: Path
) -> Path:
    """
    Resolve SQL file path (absolute or relative to sql folder).
    
    Args:
        sql_file_path: SQL file path (absolute or relative)
        sql_folder: Base SQL folder path
        
    Returns:
        Resolved absolute Path
        
    Raises:
        FileNotFoundError: If file doesn't exist
    """
    path = Path(sql_file_path)
    if not path.is_absolute():
        path = sql_folder / path
    
    if not path.exists():
        raise FileNotFoundError(f"SQL file not found: {path}")
    
    return path


def read_sql_file(file_path: Path, encoding: str = 'utf-8') -> str:
    """
    Read SQL file content.
    
    Args:
        file_path: Path to SQL file
        encoding: File encoding (default: utf-8)
        
    Returns:
        File content as string
        
    Raises:
        IOError: If file cannot be read
    """
    with open(file_path, 'r', encoding=encoding) as f:
        return f.read()

