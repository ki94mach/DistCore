"""Main SQL executor service - unified interface for executing stored procedures and SQL scripts."""

from pathlib import Path
from typing import Optional, Dict, Any, List, Union
from typing import TYPE_CHECKING

from .procedure_executor import ProcedureExecutor
from .sql_file_executor import SQLFileExecutor

if TYPE_CHECKING:
    from ..factory import DBConnectionFactory


class SQLExecutor:
    """
    Unified facade for executing SQL stored procedures and scripts.
    
    Provides a single API that delegates to specialized executors:
    - ProcedureExecutor: For stored procedure execution
    - SQLFileExecutor: For SQL file execution
    
    This facade maintains backward compatibility and provides a clean public API.
    """
    
    def __init__(self, connection_factory: 'DBConnectionFactory', sql_folder: Optional[Path] = None):
        """
        Initialize the SQL executor.
        
        Args:
            connection_factory: DBConnectionFactory instance for getting connections
            sql_folder: Optional path to the sql folder. If None, auto-detects.
        """
        self._procedure_executor = ProcedureExecutor(connection_factory)
        self._file_executor = SQLFileExecutor(connection_factory, sql_folder)
    
    def execute_procedure(
        self,
        procedure_name: str,
        parameters: Optional[Dict[str, Any]] = None,
        database_type: str = 'test',
        fetch_results: bool = True
    ) -> Optional[List[Dict[str, Any]]]:
        """
        Execute a stored procedure by name.
        
        Args:
            procedure_name: Full procedure name (e.g., '[Data].[etl_usp_run_factory_inventory_pipeline]')
            parameters: Dictionary of parameter names (without @) to values
                       Example: {'snapshot_date': '2024-01-15', 'triggered_by': 'SCHEDULED_JOB'}
            database_type: Type of database to execute against ('source' or 'test')
            fetch_results: If True, fetch and return result sets. If False, just execute.
            
        Returns:
            List of dictionaries representing rows (if fetch_results=True and procedure returns data)
            None if fetch_results=False or procedure returns no data
            
        Raises:
            pyodbc.Error: If execution fails
        """
        return self._procedure_executor.execute(
            procedure_name=procedure_name,
            parameters=parameters,
            database_type=database_type,
            fetch_results=fetch_results
        )
    
    def execute_procedure_with_output(
        self,
        procedure_name: str,
        parameters: Optional[Dict[str, Any]] = None,
        output_parameters: Optional[List[str]] = None,
        database_type: str = 'test'
    ) -> Dict[str, Any]:
        """
        Execute a stored procedure and capture output parameters.
        
        Args:
            procedure_name: Full procedure name
            parameters: Dictionary of input parameter names to values
            output_parameters: List of output parameter names (without @)
            database_type: Type of database to execute against
            
        Returns:
            Dictionary containing output parameter values and any result sets
            
        Example:
            result = executor.execute_procedure_with_output(
                '[Data].[ctl_usp_start_batch]',
                parameters={'batch_type': 'FACTORY_INVENTORY', 'triggered_by': 'SCHEDULED_JOB'},
                output_parameters=['batch_id']
            )
            batch_id = result['batch_id']
        """
        return self._procedure_executor.execute_with_output(
            procedure_name=procedure_name,
            parameters=parameters,
            output_parameters=output_parameters,
            database_type=database_type
        )
    
    def execute_sql_file(
        self,
        sql_file_path: Union[str, Path],
        database_type: str,
        parameters: Optional[Dict[str, str]] = None
    ) -> Optional[List[Dict[str, Any]]]:
        """
        Execute a SQL file from the sql folder.
        
        Args:
            sql_file_path: Path to SQL file (relative to sql folder or absolute)
            database_type: Type of database to execute against
            parameters: Optional dictionary for parameter substitution (key-value pairs)
                       Note: This is basic string substitution. For parameterized queries,
                       use stored procedures instead.
            
        Returns:
            List of dictionaries representing result rows, or None if no results
            
        Raises:
            FileNotFoundError: If SQL file doesn't exist
            pyodbc.Error: If execution fails
        """
        return self._file_executor.execute(
            sql_file_path=sql_file_path,
            database_type=database_type,
            parameters=parameters
        )

