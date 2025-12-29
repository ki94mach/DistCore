"""Executor for stored procedure calls."""

import pyodbc
from typing import Optional, Dict, Any, List, Tuple
from typing import TYPE_CHECKING

from .sql_utils import (
    clean_parameter_name,
    build_procedure_exec_sql,
    build_procedure_exec_with_output_sql,
    build_output_parameter_declarations,
    build_output_parameter_select
)
from .result_formatter import (
    format_result_set,
    format_output_parameters,
    format_all_result_sets
)

if TYPE_CHECKING:
    from ..factory import DBConnectionFactory


class ProcedureExecutor:
    """Handles execution of SQL Server stored procedures."""
    
    def __init__(self, connection_factory: 'DBConnectionFactory'):
        """
        Initialize the procedure executor.
        
        Args:
            connection_factory: DBConnectionFactory instance
        """
        self._connection_factory = connection_factory
    
    def execute(
        self,
        procedure_name: str,
        parameters: Optional[Dict[str, Any]] = None,
        database_type: str = 'source',
        fetch_results: bool = True
    ) -> Optional[List[Dict[str, Any]]]:
        """
        Execute a stored procedure.
        
        Args:
            procedure_name: Full procedure name
            parameters: Dictionary of parameter names to values
            database_type: Database type ('source' or 'test')
            fetch_results: Whether to fetch and return result sets
            
        Returns:
            List of dictionaries representing rows, or None
            
        Raises:
            pyodbc.Error: If execution fails
        """
        with self._connection_factory.connection(database_type) as conn:
            cursor = conn.cursor()
            exec_sql, param_values = self._build_exec_statement(
                procedure_name, parameters
            )
            
            try:
                cursor.execute(exec_sql, param_values)
                
                if fetch_results:
                    results = format_result_set(cursor)
                    conn.commit()
                    return results
                else:
                    conn.commit()
                    return None
                    
            except pyodbc.Error as e:
                conn.rollback()
                raise self._create_error(procedure_name, e)
    
    def execute_with_output(
        self,
        procedure_name: str,
        parameters: Optional[Dict[str, Any]] = None,
        output_parameters: Optional[List[str]] = None,
        database_type: str = 'source'
    ) -> Dict[str, Any]:
        """
        Execute a stored procedure and capture output parameters.
        
        Args:
            procedure_name: Full procedure name
            parameters: Dictionary of input parameter names to values
            output_parameters: List of output parameter names (without @)
            database_type: Database type ('source' or 'test')
            
        Returns:
            Dictionary containing output parameters and result sets
            
        Raises:
            pyodbc.Error: If execution fails
        """
        with self._connection_factory.connection(database_type) as conn:
            cursor = conn.cursor()
            full_sql, param_values, output_vars = self._build_exec_with_output_statement(
                procedure_name, parameters, output_parameters or []
            )
            
            try:
                cursor.execute(full_sql, param_values)
                
                results = self._extract_output_parameters(
                    cursor, output_vars.keys() if output_vars else []
                )
                
                # Fetch additional result sets
                additional_results = format_all_result_sets(cursor)
                if additional_results:
                    results['result_set'] = [
                        row for result_set in additional_results for row in result_set
                    ]
                
                conn.commit()
                return results
                
            except pyodbc.Error as e:
                conn.rollback()
                raise self._create_error(procedure_name, e)
    
    def _build_exec_statement(
        self,
        procedure_name: str,
        parameters: Optional[Dict[str, Any]]
    ) -> Tuple[str, List[Any]]:
        """
        Build EXEC statement and parameter values.
        
        Returns:
            Tuple of (SQL statement, parameter values list)
        """
        if not parameters:
            return build_procedure_exec_sql(procedure_name, []), []
        
        param_names = [clean_parameter_name(name) for name in parameters.keys()]
        param_values = list(parameters.values())
        exec_sql = build_procedure_exec_sql(procedure_name, param_names)
        
        return exec_sql, param_values
    
    def _build_exec_with_output_statement(
        self,
        procedure_name: str,
        parameters: Optional[Dict[str, Any]],
        output_parameters: List[str]
    ) -> Tuple[str, List[Any], Dict[str, str]]:
        """
        Build EXEC statement with output parameters.
        
        Returns:
            Tuple of (full SQL statement, parameter values, output variables dict)
        """
        sql_parts = []
        output_vars = {}
        
        # Build output parameter declarations
        if output_parameters:
            clean_output_params = [clean_parameter_name(p) for p in output_parameters]
            declarations = build_output_parameter_declarations(clean_output_params)
            sql_parts.extend(declarations)
            
            for param_name in clean_output_params:
                output_vars[param_name] = f"@{param_name}_out"
        
        # Build EXEC statement
        input_param_names = []
        param_values = []
        
        if parameters:
            input_param_names = [clean_parameter_name(name) for name in parameters.keys()]
            param_values = list(parameters.values())
        
        exec_sql = build_procedure_exec_with_output_sql(
            procedure_name,
            input_param_names,
            list(output_vars.keys()),
            output_vars
        )
        
        # Add SELECT for output parameters
        if output_vars:
            select_sql = build_output_parameter_select(output_vars)
            exec_sql += "; " + select_sql
        
        # Combine all SQL
        full_sql = "\n".join(sql_parts) + "\n" + exec_sql if sql_parts else exec_sql
        
        return full_sql, param_values, output_vars
    
    def _extract_output_parameters(
        self,
        cursor: pyodbc.Cursor,
        output_param_names: List[str]
    ) -> Dict[str, Any]:
        """Extract output parameters from cursor result set."""
        if not output_param_names:
            return {}
        
        return format_output_parameters(cursor, output_param_names)
    
    @staticmethod
    def _create_error(procedure_name: str, original_error: pyodbc.Error) -> pyodbc.Error:
        """Create a descriptive error message."""
        return pyodbc.Error(
            f"Failed to execute procedure {procedure_name}: {str(original_error)}"
        ) from original_error

