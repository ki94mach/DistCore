"""Executor for SQL file execution."""

import pyodbc
from pathlib import Path
from typing import Optional, Dict, Any, List, Union
from typing import TYPE_CHECKING

from .sql_utils import (
    resolve_sql_file_path,
    read_sql_file,
    substitute_parameters,
    split_sql_statements
)
from .result_formatter import format_result_set

if TYPE_CHECKING:
    from ..factory import DBConnectionFactory


class SQLFileExecutor:
    """Handles execution of SQL files."""
    
    def __init__(
        self,
        connection_factory: 'DBConnectionFactory',
        sql_folder: Optional[Path] = None
    ):
        """
        Initialize the SQL file executor.
        
        Args:
            connection_factory: DBConnectionFactory instance
            sql_folder: Optional path to SQL folder. If None, auto-detects from project root.
        """
        self._connection_factory = connection_factory
        self._sql_folder = sql_folder or self._get_default_sql_folder()
    
    @staticmethod
    def _get_default_sql_folder() -> Path:
        """
        Get the default path to the sql folder.
        Assumes sql folder is at the project root.
        """
        from pathlib import Path
        # Navigate from executors/ to project root
        current_file_directory = Path(__file__).parent
        # Go up: executors -> sql_server_db -> services -> orchestrator -> src -> project root
        project_root = current_file_directory.parent.parent.parent.parent.parent
        sql_folder = project_root / 'sql'
        
        if not sql_folder.exists():
            # Fallback: try one more level up if structure is different
            sql_folder = project_root.parent / 'sql'
        
        return sql_folder
    
    def execute(
        self,
        sql_file_path: Union[str, Path],
        database_type: str = 'source',
        parameters: Optional[Dict[str, str]] = None
    ) -> Optional[List[Dict[str, Any]]]:
        """
        Execute a SQL file.
        
        Args:
            sql_file_path: Path to SQL file (relative to sql folder or absolute)
            database_type: Database type ('source' or 'test')
            parameters: Optional dictionary for parameter substitution
            
        Returns:
            List of dictionaries representing result rows, or None
            
        Raises:
            FileNotFoundError: If SQL file doesn't exist
            pyodbc.Error: If execution fails
        """
        sql_path = resolve_sql_file_path(sql_file_path, self._sql_folder)
        sql_content = read_sql_file(sql_path)
        
        # Substitute parameters if provided
        if parameters:
            sql_content = substitute_parameters(sql_content, parameters)
        
        # Split into individual statements
        statements = split_sql_statements(sql_content)
        
        return self._execute_statements(statements, database_type, sql_path)
    
    def _execute_statements(
        self,
        statements: List[str],
        database_type: str,
        sql_path: Path
    ) -> Optional[List[Dict[str, Any]]]:
        """
        Execute a list of SQL statements.
        
        Args:
            statements: List of SQL statement strings
            database_type: Database type
            sql_path: Path to SQL file (for error messages)
            
        Returns:
            Result from last statement, or None
            
        Raises:
            pyodbc.Error: If execution fails
        """
        with self._connection_factory.connection(database_type) as conn:
            cursor = conn.cursor()
            results = None
            
            try:
                for statement in statements:
                    if not statement:
                        continue
                    
                    cursor.execute(statement)
                    results = format_result_set(cursor)
                
                conn.commit()
                return results
                
            except pyodbc.Error as e:
                conn.rollback()
                raise self._create_error(sql_path, e)
    
    @staticmethod
    def _create_error(sql_path: Path, original_error: pyodbc.Error) -> pyodbc.Error:
        """Create a descriptive error message."""
        error_msg = f"Failed to execute SQL file {sql_path}: {str(original_error)}"
        new_error = pyodbc.Error(error_msg)
        new_error.__cause__ = original_error
        return new_error
