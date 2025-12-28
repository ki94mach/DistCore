import yaml
import pyodbc
import threading
from pathlib import Path


class DBConnectionFactory:
    """
    Singleton database connection factory that loads configuration from db.yml
    and provides thread-safe database connections.
    """
    _instance = None
    _lock = threading.Lock()
    _config = None
    
    def __new__(cls):
        """Thread-safe singleton pattern implementation."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super(DBConnectionFactory, cls).__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        """Initialize the factory by loading configuration."""
        if self._initialized:
            return
        
        with self._lock:
            if self._initialized:
                return
            
            self._load_config()
            self._initialized = True
    
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
    
    def get_connection(self, database_type: str = 'source'):
        """
        Get a database connection for the specified database type.
        
        Args:
            database_type: Type of database ('source' or 'test')
        
        Returns:
            pyodbc.Connection: Database connection object
        
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
            return connection
        except pyodbc.Error as e:
            raise pyodbc.Error(
                f"Failed to connect to {database_type} database ({server}/{database}): {str(e)}"
            ) from e
    
    def get_source_connection(self):
        """Get a connection to the source database."""
        return self.get_connection('source')
    
    def get_test_connection(self):
        """Get a connection to the test database."""
        return self.get_connection('test')
    
    def get_config(self):
        """Get the loaded configuration (read-only)."""
        return self._config.copy() if self._config else None