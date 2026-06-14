"""Configuration loading and validation for database connections."""

import yaml
from pathlib import Path
from typing import Dict, Any

DEFAULT_DATABASE_TYPE = "prod"
SOURCE_DATABASE_TYPE = "source"
DB_CONNECTION_CONFIG_KEYS = frozenset(
    {"driver", "username", "password", "use_windows_auth"}
)


class DBConfigLoader:
    """Responsible for loading and validating database configuration from YAML file."""
    
    def __init__(self, config_file_path: Path):
        """
        Initialize the config loader.
        
        Args:
            config_file_path: Path to the database configuration YAML file
        """
        self._config_file_path = config_file_path
        self._config = None
    
    def load_config(self) -> Dict[str, Any]:
        """
        Load and validate database configuration.
        
        Returns:
            Dictionary containing the loaded configuration
            
        Raises:
            FileNotFoundError: If configuration file doesn't exist
            ValueError: If configuration is invalid
        """
        self._validate_config_file_exists()
        self._load_yaml_config()
        self._validate_config_structure()
        return self._config
    
    def _validate_config_file_exists(self) -> None:
        """Validate that the configuration file exists."""
        if not self._config_file_path.exists():
            raise FileNotFoundError(
                f"Configuration file not found: {self._config_file_path}"
            )
    
    def _load_yaml_config(self) -> None:
        """Load configuration from YAML file."""
        with open(self._config_file_path, 'r') as config_file:
            self._config = yaml.safe_load(config_file)
    
    def _validate_config_structure(self) -> None:
        """Validate that the configuration has the required structure."""
        if not self._config or 'databases' not in self._config:
            raise ValueError("Invalid configuration: 'databases' key not found")

        databases = self._config['databases']
        connection_keys = [
            key for key in databases
            if isinstance(databases.get(key), dict) and 'server' in databases[key]
        ]
        for key in connection_keys:
            db_config = databases[key]
            if 'database' not in db_config:
                raise ValueError(
                    f"Invalid configuration: '{key}' connection missing 'database'"
                )
            schema = db_config.get('schema', 'Data')
            if not schema or not isinstance(schema, str):
                raise ValueError(
                    f"Invalid configuration: '{key}.schema' must be a non-empty string"
                )

