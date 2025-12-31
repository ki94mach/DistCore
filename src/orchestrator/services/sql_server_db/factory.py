"""Main database connection factory."""

import pyodbc
import threading
import time
from pathlib import Path
from typing import Optional, Dict, Any, TYPE_CHECKING

from .config import DBConfigLoader
from .connection_string import ConnectionStringBuilder
from .health import ConnectionHealthChecker
from .metadata import ConnectionMetadataManager
from .pool import ConnectionPoolManager

if TYPE_CHECKING:
    from .context import ConnectionContextManager


class DBConnectionFactory:
    """
    Singleton factory for creating and managing database connections.
    Follows Single Responsibility Principle by delegating to specialized classes.
    
    Can be initialized in multiple ways:
    1. Default: Uses default config path (backward compatible)
    2. With config_path: Pass a Path to config file
    3. With config_dict: Pass configuration dictionary directly
    """
    _instance = None
    _singleton_lock = threading.Lock()
    
    def __init__(
        self,
        config_path: Optional[Path] = None,
        config_dict: Optional[Dict[str, Any]] = None
    ):
        """
        Initialize the factory by loading configuration and setting up components.
        
        Args:
            config_path: Optional path to configuration YAML file. If None, uses default path.
            config_dict: Optional configuration dictionary. If provided, config_path is ignored.
                        This allows using the factory without a YAML file.
        """
        if self._initialized:
            return
        
        with self._singleton_lock:
            if self._initialized:
                return
            
            self._initialize_factory_components(config_path, config_dict)
            self._initialized = True
    
    def __new__(cls, config_path: Optional[Path] = None, config_dict: Optional[Dict[str, Any]] = None):
        """Thread-safe singleton pattern implementation."""
        if cls._instance is None:
            with cls._singleton_lock:
                if cls._instance is None:
                    cls._instance = super(DBConnectionFactory, cls).__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def _initialize_factory_components(
        self,
        config_path: Optional[Path] = None,
        config_dict: Optional[Dict[str, Any]] = None
    ) -> None:
        """Initialize all factory components with configuration."""
        if config_dict is not None:
            self._config = config_dict
        else:
            config_file_path = config_path or self._get_default_config_file_path()
            config_loader = DBConfigLoader(config_file_path)
            self._config = config_loader.load_config()
        
        self._connection_string_builder = ConnectionStringBuilder(
            self._config['databases']
        )
        self._connection_health_checker = ConnectionHealthChecker()
        self._connection_metadata_manager = ConnectionMetadataManager()
        self._connection_pool_manager = ConnectionPoolManager()
    
    def _get_default_config_file_path(self) -> Path:
        """
        Get the default path to the database configuration file.
        This maintains backward compatibility with the original project structure.
        """
        current_file_directory = Path(__file__).parent.parent
        return current_file_directory.parent / 'config' / 'db.yml'
    
    @classmethod
    def from_config_file(cls, config_path: Path) -> 'DBConnectionFactory':
        """
        Create a factory instance from a configuration file.
        
        Args:
            config_path: Path to the configuration YAML file
            
        Returns:
            DBConnectionFactory instance
            
        Example:
            factory = DBConnectionFactory.from_config_file(Path('/path/to/config.yml'))
        """
        return cls(config_path=config_path)
    
    @classmethod
    def from_config_dict(cls, config_dict: Dict[str, Any]) -> 'DBConnectionFactory':
        """
        Create a factory instance from a configuration dictionary.
        
        Args:
            config_dict: Configuration dictionary with 'databases' key
            
        Returns:
            DBConnectionFactory instance
            
        Example:
            config = {
                'databases': {
                    'driver': 'ODBC Driver 17 for SQL Server',
                    'use_windows_auth': True,
                    'source': {
                        'server': 'myserver',
                        'database': 'mydb'
                    }
                }
            }
            factory = DBConnectionFactory.from_config_dict(config)
        """
        return cls(config_dict=config_dict)
    
    def get_connection(
        self,
        database_type: str = 'test',
        use_pool: bool = True
    ) -> pyodbc.Connection:
        """
        Get a database connection for the specified database type.
        
        Args:
            database_type: Type of database ('source' or 'test')
            use_pool: If True, reuse connections from pool. If False, create new connection.
            
        Returns:
            Database connection object
            
        Raises:
            ValueError: If database_type is not found in configuration
            pyodbc.Error: If connection fails
        """
        if not use_pool:
            return self._create_new_connection(database_type)
        
        return self._get_connection_from_pool_or_create_new(database_type)
    
    def _get_connection_from_pool_or_create_new(
        self,
        database_type: str
    ) -> pyodbc.Connection:
        """Get connection from pool or create a new one if pool is empty."""
        pooled_connection = self._connection_pool_manager.get_connection_from_pool(
            database_type=database_type,
            metadata_manager=self._connection_metadata_manager,
            health_checker=self._connection_health_checker
        )
        
        if pooled_connection is not None:
            return pooled_connection
        
        return self._create_new_connection(database_type)
    
    def _create_new_connection(self, database_type: str) -> pyodbc.Connection:
        """
        Create a new database connection.
        
        Args:
            database_type: Type of database to connect to
            
        Returns:
            New database connection object
            
        Raises:
            ValueError: If database_type is not found in configuration
            pyodbc.Error: If connection fails
        """
        self._validate_database_type_exists(database_type)
        
        database_config = self._config['databases'][database_type]
        server_name = database_config['server']
        database_name = database_config['database']
        
        connection_string = self._connection_string_builder.build_connection_string(
            server_name=server_name,
            database_name=database_name
        )
        
        return self._establish_database_connection(
            connection_string, database_type, server_name, database_name
        )
    
    def _validate_database_type_exists(self, database_type: str) -> None:
        """Validate that the database type exists in configuration."""
        if database_type not in self._config['databases']:
            available_types = list(self._config['databases'].keys())
            raise ValueError(
                f"Database type '{database_type}' not found in configuration. "
                f"Available types: {available_types}"
            )
    
    def _establish_database_connection(
        self,
        connection_string: str,
        database_type: str,
        server_name: str,
        database_name: str
    ) -> pyodbc.Connection:
        """
        Establish a new database connection and store its metadata.
        
        Args:
            connection_string: Complete ODBC connection string
            database_type: Type of database
            server_name: Name of the server
            database_name: Name of the database
            
        Returns:
            New database connection
            
        Raises:
            pyodbc.Error: If connection fails
        """
        try:
            new_connection = pyodbc.connect(connection_string)
            current_timestamp = time.time()
            
            self._connection_metadata_manager.store_metadata(
                connection=new_connection,
                database_type=database_type,
                created_at_timestamp=current_timestamp
            )
            
            return new_connection
        except pyodbc.Error as connection_error:
            raise pyodbc.Error(
                f"Failed to connect to {database_type} database "
                f"({server_name}/{database_name}): {str(connection_error)}"
            ) from connection_error
    
    def return_connection(self, connection: pyodbc.Connection) -> None:
        """
        Return a connection to the pool for reuse.
        
        Args:
            connection: The connection to return to the pool
        """
        database_type = self._connection_metadata_manager.get_metadata(
            connection, '_db_type'
        )
        
        if not database_type:
            self._close_connection_safely(connection)
            return
        
        self._connection_pool_manager.return_connection_to_pool(
            connection=connection,
            database_type=database_type,
            metadata_manager=self._connection_metadata_manager,
            health_checker=self._connection_health_checker
        )
    
    def close_all_connections(
        self,
        database_type: Optional[str] = None
    ) -> None:
        """
        Close all connections in the pool(s).
        
        Args:
            database_type: If specified, close only connections for this type.
                          If None, close all connections for all database types.
        """
        self._connection_pool_manager.close_all_connections_in_pool(database_type)
    
    def get_source_connection(self) -> pyodbc.Connection:
        """Get a connection to the source database."""
        return self.get_connection('source')
    
    def get_test_connection(self) -> pyodbc.Connection:
        """Get a connection to the test database."""
        return self.get_connection('test')
    
    def get_config(self) -> Optional[Dict[str, Any]]:
        """Get the loaded configuration (read-only)."""
        return self._config.copy() if self._config else None
    
    def connection(self, database_type: str = 'test') -> 'ConnectionContextManager':  # type: ignore
        """
        Context manager for automatic connection management.
        
        Usage:
            with factory.connection('source') as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM table")
        
        Args:
            database_type: Type of database ('source' or 'test')
            
        Returns:
            ConnectionContextManager that handles connection lifecycle
        """
        from .context import ConnectionContextManager
        return ConnectionContextManager(self, database_type)
    
    @staticmethod
    def _close_connection_safely(connection: pyodbc.Connection) -> None:
        """Safely close a connection, ignoring any errors."""
        try:
            connection.close()
        except:
            pass

