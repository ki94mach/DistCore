"""Connection pool management for database connections."""

import pyodbc
import threading
import time
from typing import Optional, Dict
from queue import Queue, Empty

from .metadata import ConnectionMetadataManager
from .health import ConnectionHealthChecker


class ConnectionPoolManager:
    """Responsible for managing connection pools for different database types."""
    
    def __init__(
        self,
        max_pool_size: int = 10,
        connection_timeout_seconds: int = 300
    ):
        """
        Initialize the connection pool manager.
        
        Args:
            max_pool_size: Maximum number of connections per pool
            connection_timeout_seconds: Timeout in seconds before connections are refreshed
        """
        self._max_pool_size = max_pool_size
        self._connection_timeout_seconds = connection_timeout_seconds
        self._connection_pools: Dict[str, Queue] = {}
        self._pool_locks: Dict[str, threading.Lock] = {}
        self._initialization_lock = threading.Lock()
    
    def get_connection_from_pool(
        self,
        database_type: str,
        metadata_manager: ConnectionMetadataManager,
        health_checker: ConnectionHealthChecker
    ) -> Optional[pyodbc.Connection]:
        """
        Get a connection from the pool, or None if pool is empty or connections are stale.
        
        Args:
            database_type: Type of database to get connection for
            metadata_manager: Manager for connection metadata
            health_checker: Checker for connection health
            
        Returns:
            A valid connection from pool, or None if none available
        """
        connection_pool = self._get_or_create_pool(database_type)
        pool_lock = self._get_pool_lock(database_type)
        
        with pool_lock:
            return self._try_get_valid_connection_from_pool(
                connection_pool,
                database_type,
                metadata_manager,
                health_checker
            )
    
    def return_connection_to_pool(
        self,
        connection: pyodbc.Connection,
        database_type: str,
        metadata_manager: ConnectionMetadataManager,
        health_checker: ConnectionHealthChecker
    ) -> None:
        """
        Return a connection to the pool if it's still valid.
        
        Args:
            connection: The connection to return
            database_type: Type of database
            metadata_manager: Manager for connection metadata
            health_checker: Checker for connection health
        """
        if not self._is_connection_valid_for_pool(
            connection, database_type, metadata_manager, health_checker
        ):
            self._close_connection_safely(connection)
            return
        
        connection_pool = self._get_or_create_pool(database_type)
        pool_lock = self._get_pool_lock(database_type)
        
        with pool_lock:
            self._try_add_connection_to_pool(connection_pool, connection)
    
    def close_all_connections_in_pool(
        self,
        database_type: Optional[str] = None
    ) -> None:
        """
        Close all connections in the specified pool(s).
        
        Args:
            database_type: If specified, close only this type. If None, close all.
        """
        database_types_to_close = (
            [database_type] if database_type
            else list(self._connection_pools.keys())
        )
        
        for db_type in database_types_to_close:
            self._close_all_connections_for_database_type(db_type)
    
    def _get_or_create_pool(self, database_type: str) -> Queue:
        """Get existing pool or create a new one for the database type."""
        if database_type not in self._connection_pools:
            with self._initialization_lock:
                if database_type not in self._connection_pools:
                    self._connection_pools[database_type] = Queue(
                        maxsize=self._max_pool_size
                    )
                    self._pool_locks[database_type] = threading.Lock()
        
        return self._connection_pools[database_type]
    
    def _get_pool_lock(self, database_type: str) -> threading.Lock:
        """Get the lock for the specified database type's pool."""
        return self._pool_locks[database_type]
    
    def _try_get_valid_connection_from_pool(
        self,
        connection_pool: Queue,
        database_type: str,
        metadata_manager: ConnectionMetadataManager,
        health_checker: ConnectionHealthChecker
    ) -> Optional[pyodbc.Connection]:
        """Try to get a valid connection from the pool."""
        try:
            connection = connection_pool.get_nowait()
            if self._is_connection_stale(
                connection, metadata_manager
            ) or not health_checker.is_connection_alive(connection):
                self._close_connection_safely(connection)
                return None
            return connection
        except Empty:
            return None
    
    def _is_connection_stale(
        self,
        connection: pyodbc.Connection,
        metadata_manager: ConnectionMetadataManager
    ) -> bool:
        """Check if a connection is too old and should be refreshed."""
        current_timestamp = time.time()
        created_at_timestamp = metadata_manager.get_metadata(
            connection, '_created_at', current_timestamp
        )
        connection_age_seconds = current_timestamp - created_at_timestamp
        return connection_age_seconds > self._connection_timeout_seconds
    
    def _is_connection_valid_for_pool(
        self,
        connection: pyodbc.Connection,
        database_type: str,
        metadata_manager: ConnectionMetadataManager,
        health_checker: ConnectionHealthChecker
    ) -> bool:
        """Check if a connection is valid and can be returned to the pool."""
        stored_database_type = metadata_manager.get_metadata(connection, '_db_type')
        if not stored_database_type or stored_database_type != database_type:
            return False
        
        return health_checker.is_connection_alive(connection)
    
    def _try_add_connection_to_pool(
        self,
        connection_pool: Queue,
        connection: pyodbc.Connection
    ) -> None:
        """Try to add a connection to the pool, close it if pool is full."""
        try:
            connection_pool.put_nowait(connection)
        except:
            # Pool is full, close the connection
            self._close_connection_safely(connection)
    
    def _close_all_connections_for_database_type(self, database_type: str) -> None:
        """Close all connections in the pool for a specific database type."""
        if database_type not in self._connection_pools:
            return
        
        connection_pool = self._connection_pools[database_type]
        pool_lock = self._pool_locks[database_type]
        
        with pool_lock:
            while not connection_pool.empty():
                try:
                    connection = connection_pool.get_nowait()
                    self._close_connection_safely(connection)
                except Empty:
                    break
    
    @staticmethod
    def _close_connection_safely(connection: pyodbc.Connection) -> None:
        """Safely close a connection, ignoring any errors."""
        try:
            connection.close()
        except:
            pass

