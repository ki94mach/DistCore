"""Connection metadata management for database connections."""

import pyodbc
from typing import Dict, Any


class ConnectionMetadataManager:
    """Responsible for managing metadata associated with database connections."""
    
    def __init__(self):
        """Initialize the metadata manager."""
        self._metadata_storage: Dict[int, Dict[str, Any]] = {}
    
    def store_metadata(
        self,
        connection: pyodbc.Connection,
        database_type: str,
        created_at_timestamp: float
    ) -> None:
        """
        Store metadata for a connection.
        
        Args:
            connection: The database connection
            database_type: Type of database (e.g., 'source', 'prod')
            created_at_timestamp: Timestamp when connection was created
        """
        if self._can_store_attributes_on_connection():
            self._store_metadata_on_connection(
                connection, database_type, created_at_timestamp
            )
        else:
            self._store_metadata_in_dictionary(
                connection, database_type, created_at_timestamp
            )
    
    def get_metadata(
        self,
        connection: pyodbc.Connection,
        metadata_key: str,
        default_value: Any = None
    ) -> Any:
        """
        Retrieve metadata for a connection.
        
        Args:
            connection: The database connection
            metadata_key: Key of the metadata to retrieve
            default_value: Default value if metadata not found
            
        Returns:
            The metadata value or default value
        """
        if self._has_metadata_on_connection(connection, metadata_key):
            return getattr(connection, metadata_key, default_value)
        
        return self._get_metadata_from_dictionary(
            connection, metadata_key, default_value
        )
    
    def _can_store_attributes_on_connection(self) -> bool:
        """Check if we can store attributes directly on connection object."""
        # This will be tested when we try to set attributes
        return True
    
    def _store_metadata_on_connection(
        self,
        connection: pyodbc.Connection,
        database_type: str,
        created_at_timestamp: float
    ) -> None:
        """Attempt to store metadata directly on connection object."""
        try:
            setattr(connection, '_db_type', database_type)
            setattr(connection, '_created_at', created_at_timestamp)
        except (AttributeError, TypeError):
            self._store_metadata_in_dictionary(
                connection, database_type, created_at_timestamp
            )
    
    def _store_metadata_in_dictionary(
        self,
        connection: pyodbc.Connection,
        database_type: str,
        created_at_timestamp: float
    ) -> None:
        """Store metadata in internal dictionary as fallback."""
        connection_id = id(connection)
        self._metadata_storage[connection_id] = {
            '_db_type': database_type,
            '_created_at': created_at_timestamp
        }
    
    def _has_metadata_on_connection(
        self,
        connection: pyodbc.Connection,
        metadata_key: str
    ) -> bool:
        """Check if metadata exists as attribute on connection object."""
        return hasattr(connection, metadata_key)
    
    def _get_metadata_from_dictionary(
        self,
        connection: pyodbc.Connection,
        metadata_key: str,
        default_value: Any
    ) -> Any:
        """Retrieve metadata from internal dictionary."""
        connection_id = id(connection)
        if connection_id in self._metadata_storage:
            return self._metadata_storage[connection_id].get(metadata_key, default_value)
        return default_value

