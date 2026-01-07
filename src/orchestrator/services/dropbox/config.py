"""Configuration loading for Dropbox shared links."""

import yaml
from pathlib import Path
from typing import Optional, Dict, Any


class DropboxConfigLoader:
    """
    Responsible for loading Dropbox configuration (shared links) from YAML config file.
    """
    
    @staticmethod
    def _get_default_config_file_path() -> Path:
        """
        Get the default path to the Dropbox configuration file.
        """
        current_file_directory = Path(__file__).parent.parent.parent
        return current_file_directory / 'config' / 'dropbox.yml'
    
    @staticmethod
    def load_config(config_file_path: Optional[Path] = None) -> Dict[str, Any]:
        """
        Load Dropbox configuration from YAML configuration file.
        
        Args:
            config_file_path: Optional path to configuration YAML file. 
                            If None, uses default path.
        
        Returns:
            Dictionary containing configuration (e.g., {'distributor_deliveries_folder': 'https://...'})
        
        Raises:
            FileNotFoundError: If configuration file doesn't exist
            ValueError: If configuration is invalid
        """
        config_path = config_file_path or DropboxConfigLoader._get_default_config_file_path()
        
        if not config_path.exists():
            raise FileNotFoundError(
                f"Dropbox configuration file not found: {config_path}\n"
                f"Please create the config file with shared link URLs."
            )
        
        with open(config_path, 'r', encoding='utf-8') as config_file:
            config = yaml.safe_load(config_file)
        
        if not config or 'dropbox' not in config:
            raise ValueError("Invalid Dropbox configuration: 'dropbox' key not found")
        
        return config['dropbox']
    
    @staticmethod
    def get_shared_link(key: str, config_file_path: Optional[Path] = None) -> str:
        """
        Get a shared link from the configuration by key.
        
        Args:
            key: Configuration key (e.g., 'distributor_deliveries_folder')
            config_file_path: Optional path to configuration YAML file.
                            If None, uses default path.
        
        Returns:
            Shared link URL string
        
        Raises:
            FileNotFoundError: If configuration file doesn't exist
            ValueError: If configuration is invalid or key not found
        """
        config = DropboxConfigLoader.load_config(config_file_path)
        
        if key not in config:
            raise ValueError(
                f"Configuration key '{key}' not found in Dropbox configuration"
            )
        
        return config[key]
    
    @staticmethod
    def get_distributor_deliveries_folder(config_file_path: Optional[Path] = None) -> str:
        """
        Get the distributor deliveries folder shared link from configuration.
        
        Args:
            config_file_path: Optional path to configuration YAML file.
                            If None, uses default path.
        
        Returns:
            Shared link URL string
        
        Raises:
            FileNotFoundError: If configuration file doesn't exist
            ValueError: If configuration is invalid or folder path not found
        """
        return DropboxConfigLoader.get_shared_link('distributor_deliveries_folder', config_file_path)
