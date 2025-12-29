"""Connection health checking for database connections."""

import pyodbc


class ConnectionHealthChecker:
    """Responsible for checking if database connections are alive and usable."""
    
    @staticmethod
    def is_connection_alive(connection: pyodbc.Connection) -> bool:
        """
        Check if a database connection is still alive and usable.
        
        Args:
            connection: The database connection to check
            
        Returns:
            True if connection is alive and usable, False otherwise
        """
        try:
            return ConnectionHealthChecker._execute_health_check_query(connection)
        except (pyodbc.Error, pyodbc.InterfaceError):
            return False
    
    @staticmethod
    def _execute_health_check_query(connection: pyodbc.Connection) -> bool:
        """Execute a simple query to verify connection health."""
        health_check_cursor = connection.cursor()
        try:
            health_check_cursor.execute("SELECT 1")
            health_check_cursor.fetchone()
            return True
        finally:
            health_check_cursor.close()

