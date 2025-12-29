"""Context manager for database connections."""

import pyodbc
from .factory import DBConnectionFactory


class ConnectionContextManager:
    """Context manager for database connections that automatically returns them to the pool."""
    
    def __init__(
        self,
        connection_factory: DBConnectionFactory,
        database_type: str
    ):
        """
        Initialize the context manager.
        
        Args:
            connection_factory: Factory to get connections from
            database_type: Type of database to connect to
        """
        self._connection_factory = connection_factory
        self._database_type = database_type
        self._connection = None
    
    def __enter__(self) -> pyodbc.Connection:
        """Get a connection from the factory when entering context."""
        self._connection = self._connection_factory.get_connection(
            self._database_type
        )
        return self._connection
    
    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        """
        Return connection to pool when exiting context.
        
        Args:
            exc_type: Exception type if any
            exc_val: Exception value if any
            exc_tb: Exception traceback if any
            
        Returns:
            False to not suppress exceptions
        """
        if self._connection:
            self._connection_factory.return_connection(self._connection)
        return False

