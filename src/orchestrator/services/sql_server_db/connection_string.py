"""ODBC connection string building for database connections."""

from typing import Dict, Any


class ConnectionStringBuilder:
    """Responsible for building ODBC connection strings based on configuration."""
    
    def __init__(self, database_config: Dict[str, Any]):
        """
        Initialize the connection string builder.
        
        Args:
            database_config: Database configuration dictionary
        """
        self._database_config = database_config
    
    def build_connection_string(self, server_name: str, database_name: str) -> str:
        """
        Build ODBC connection string for the given server and database.
        
        Args:
            server_name: Name of the SQL Server instance
            database_name: Name of the database
            
        Returns:
            Complete ODBC connection string
            
        Raises:
            ValueError: If SQL Server auth is required but credentials are missing
        """
        driver_name = self._get_driver_name()
        authentication_string = self._build_authentication_string()
        
        return self._assemble_connection_string(
            driver_name=driver_name,
            server_name=server_name,
            database_name=database_name,
            authentication_string=authentication_string
        )
    
    def _get_driver_name(self) -> str:
        """Extract ODBC driver name from configuration."""
        return self._database_config['driver']
    
    def _build_authentication_string(self) -> str:
        """
        Build authentication portion of connection string.
        
        Returns:
            Authentication string (either Windows Auth or SQL Server Auth)
            
        Raises:
            ValueError: If SQL Server auth is required but credentials are missing
        """
        if self._should_use_windows_authentication():
            return "Trusted_Connection=yes;"
        return self._build_sql_server_authentication_string()
    
    def _should_use_windows_authentication(self) -> bool:
        """Determine if Windows Authentication should be used."""
        use_windows_auth = self._database_config.get('use_windows_auth', False)
        username = self._database_config.get('username')
        password = self._database_config.get('password')
        
        return use_windows_auth or (not username and not password)
    
    def _build_sql_server_authentication_string(self) -> str:
        """
        Build SQL Server authentication string with username and password.
        
        Returns:
            Authentication string with UID and PWD
            
        Raises:
            ValueError: If username or password is missing
        """
        username = self._database_config.get('username')
        password = self._database_config.get('password')
        
        if not username or not password:
            raise ValueError(
                "Username and password are required when not using Windows Authentication"
            )
        
        return f"UID={username};PWD={password};"
    
    def _assemble_connection_string(
        self,
        driver_name: str,
        server_name: str,
        database_name: str,
        authentication_string: str
    ) -> str:
        """Assemble the complete ODBC connection string."""
        return (
            f"DRIVER={{{driver_name}}};"
            f"SERVER={server_name};"
            f"DATABASE={database_name};"
            f"{authentication_string}"
            f"TrustServerCertificate=yes;"
        )

