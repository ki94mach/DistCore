import yaml
import pyodbc
import threading
import time
from pathlib import Path
from typing import Optional
from queue import Queue, Empty


class DBConnectionFactory:
    """
    Singleton database connection factory that loads configuration from db.yml
    and provides thread-safe database connections with connection pooling per database type.
    """
    _instance = None
    _lock = threading.Lock()
    _config = None
    
    def __init__(self):
        """Initialize the factory by loading configuration."""
        if self._initialized:
            return
        
        with self._lock:
            if self._initialized:
                return
            
            self._load_config()
            # Connection pools: one queue per database type
            self._connection_pools = {}
            self._pool_locks = {}
            self._max_pool_size = 10  # Maximum connections per database type
            self._connection_timeout = 300  # 5 minutes - connections older than this are refreshed
            self._initialized = True
    
    def __new__(cls):
        """Thread-safe singleton pattern implementation."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super(DBConnectionFactory, cls).__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def _load_config(self):
        """Load database configuration from db.yml file."""
        # Get the path to db.yml relative to this file
        current_dir = Path(__file__).parent
        config_path = current_dir.parent / 'config' / 'db.yml'
        
        if not config_path.exists():
            raise FileNotFoundError(f"Configuration file not found: {config_path}")
        
        with open(config_path, 'r') as file:
            self._config = yaml.safe_load(file)
        
        if not self._config or 'databases' not in self._config:
            raise ValueError("Invalid configuration: 'databases' key not found")
    
    def _build_connection_string(self, server: str, database: str) -> str:
        """Build ODBC connection string from configuration."""
        driver = self._config['databases']['driver']
        username = self._config['databases']['username']
        password = self._config['databases']['password']
        
        return (
            f"DRIVER={{{driver}}};"
            f"SERVER={server};"
            f"DATABASE={database};"
            f"UID={username};"
            f"PWD={password};"
            f"TrustServerCertificate=yes;"
        )
    
    def _is_connection_alive(self, connection: pyodbc.Connection) -> bool:
        """
        Check if a connection is still alive and usable.
        
        Args:
            connection: The connection to check
        
        Returns:
            True if connection is alive, False otherwise
        """
        try:
            # Try to execute a simple query
            cursor = connection.cursor()
            cursor.execute("SELECT 1")
            cursor.fetchone()
            cursor.close()
            return True
        except (pyodbc.Error, pyodbc.InterfaceError):
            return False
    
    def _create_new_connection(self, database_type: str) -> pyodbc.Connection:
        """
        Create a new database connection.
        
        Args:
            database_type: Type of database to connect to
        
        Returns:
            pyodbc.Connection: New connection object
        
        Raises:
            ValueError: If database_type is not found in configuration
            pyodbc.Error: If connection fails
        """
        if database_type not in self._config['databases']:
            raise ValueError(
                f"Database type '{database_type}' not found in configuration. "
                f"Available types: {list(self._config['databases'].keys())}"
            )
        
        db_config = self._config['databases'][database_type]
        server = db_config['server']
        database = db_config['database']
        
        connection_string = self._build_connection_string(server, database)
        
        try:
            connection = pyodbc.connect(connection_string)
            # Store metadata on the connection object
            connection._db_type = database_type
            connection._created_at = time.time()
            return connection
        except pyodbc.Error as e:
            raise pyodbc.Error(
                f"Failed to connect to {database_type} database ({server}/{database}): {str(e)}"
            ) from e
    
    def _get_pool(self, database_type: str) -> Queue:
        """Get or create the connection pool for a database type."""
        if database_type not in self._connection_pools:
            with self._lock:
                if database_type not in self._connection_pools:
                    self._connection_pools[database_type] = Queue(maxsize=self._max_pool_size)
                    self._pool_locks[database_type] = threading.Lock()
        return self._connection_pools[database_type]
    
    def get_connection(self, database_type: str = 'source', use_pool: bool = True) -> pyodbc.Connection:
        """
        Get a database connection for the specified database type.
        Uses connection pooling by default for better performance.
        
        Args:
            database_type: Type of database ('source' or 'test')
            use_pool: If True, reuse connections from pool. If False, create new connection.
        
        Returns:
            pyodbc.Connection: Database connection object
        
        Raises:
            ValueError: If database_type is not found in configuration
            pyodbc.Error: If connection fails
        """
        if not use_pool:
            return self._create_new_connection(database_type)
        
        pool = self._get_pool(database_type)
        pool_lock = self._pool_locks[database_type]
        
        # Try to get a connection from the pool
        connection = None
        with pool_lock:
            try:
                # Try to get a connection from pool (non-blocking)
                connection = pool.get_nowait()
                
                # Check if connection is still alive and not too old
                current_time = time.time()
                is_old = (current_time - connection._created_at) > self._connection_timeout
                
                if is_old or not self._is_connection_alive(connection):
                    # Connection is stale, close it and create a new one
                    try:
                        connection.close()
                    except:
                        pass
                    connection = None
            except Empty:
                # No connection available in pool, will create new one
                pass
        
        # If no valid connection from pool, create a new one
        if connection is None:
            connection = self._create_new_connection(database_type)
        
        return connection
    
    def return_connection(self, connection: pyodbc.Connection):
        """
        Return a connection to the pool for reuse.
        Call this when you're done with a connection instead of closing it.
        
        Args:
            connection: The connection to return to the pool
        """
        if not hasattr(connection, '_db_type'):
            # Connection wasn't created by this factory, just close it
            try:
                connection.close()
            except:
                pass
            return
        
        database_type = connection._db_type
        pool = self._get_pool(database_type)
        pool_lock = self._pool_locks[database_type]
        
        # Check if connection is still alive before returning to pool
        if not self._is_connection_alive(connection):
            try:
                connection.close()
            except:
                pass
            return
        
        # Try to return to pool (non-blocking)
        with pool_lock:
            try:
                pool.put_nowait(connection)
            except:
                # Pool is full, close the connection
                try:
                    connection.close()
                except:
                    pass
    
    def close_all_connections(self, database_type: Optional[str] = None):
        """
        Close all connections in the pool(s).
        
        Args:
            database_type: If specified, close only connections for this type.
                          If None, close all connections for all database types.
        """
        types_to_close = [database_type] if database_type else list(self._connection_pools.keys())
        
        for db_type in types_to_close:
            if db_type not in self._connection_pools:
                continue
            
            pool = self._connection_pools[db_type]
            pool_lock = self._pool_locks[db_type]
            
            with pool_lock:
                while not pool.empty():
                    try:
                        conn = pool.get_nowait()
                        try:
                            conn.close()
                        except:
                            pass
                    except Empty:
                        break
    
    def get_source_connection(self):
        """Get a connection to the source database."""
        return self.get_connection('source')
    
    def get_test_connection(self):
        """Get a connection to the test database."""
        return self.get_connection('test')
    
    def get_config(self):
        """Get the loaded configuration (read-only)."""
        return self._config.copy() if self._config else None
    
    def connection(self, database_type: str = 'source'):
        """
        Context manager for automatic connection management.
        Returns connection to pool when done.
        
        Usage:
            with factory.connection('source') as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM table")
                # ... work with connection ...
        
        Args:
            database_type: Type of database ('source' or 'test')
        
        Returns:
            ConnectionContextManager: Context manager that handles connection lifecycle
        """
        return ConnectionContextManager(self, database_type)


class ConnectionContextManager:
    """Context manager for database connections that automatically returns them to the pool."""
    
    def __init__(self, factory: DBConnectionFactory, database_type: str):
        self.factory = factory
        self.database_type = database_type
        self.connection = None
    
    def __enter__(self) -> pyodbc.Connection:
        """Get a connection from the factory."""
        self.connection = self.factory.get_connection(self.database_type)
        return self.connection
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Return connection to pool when done."""
        if self.connection:
            self.factory.return_connection(self.connection)
        return False  # Don't suppress exceptions