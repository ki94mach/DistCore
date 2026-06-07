"""Configuration loading for DMS folder URLs."""

import yaml
from pathlib import Path
from typing import Any, Dict, Optional


class DmsConfigLoader:
    """Loads DMS configuration (folder URLs) from YAML config file."""

    @staticmethod
    def _get_default_config_file_path() -> Path:
        current_file_directory = Path(__file__).parent.parent.parent
        return current_file_directory / 'config' / 'dms.yml'

    @staticmethod
    def load_config(config_file_path: Optional[Path] = None) -> Dict[str, Any]:
        config_path = config_file_path or DmsConfigLoader._get_default_config_file_path()

        if not config_path.exists():
            raise FileNotFoundError(
                f"DMS configuration file not found: {config_path}\n"
                f"Please create the config file with folder URLs."
            )

        with open(config_path, 'r', encoding='utf-8') as config_file:
            config = yaml.safe_load(config_file)

        if not config or 'dms' not in config:
            raise ValueError("Invalid DMS configuration: 'dms' key not found")

        return config['dms']

    @staticmethod
    def get_distributor_deliveries_config(
        config_file_path: Optional[Path] = None,
    ) -> Dict[str, str]:
        config = DmsConfigLoader.load_config(config_file_path)

        if 'distributor_deliveries' not in config:
            raise ValueError(
                "Configuration key 'distributor_deliveries' not found in DMS configuration"
            )

        deliveries_config = config['distributor_deliveries']
        required_keys = ('historical_folder_url', 'current_folder_url')
        missing = [key for key in required_keys if key not in deliveries_config]
        if missing:
            raise ValueError(
                f"Missing DMS distributor_deliveries keys: {', '.join(missing)}"
            )

        return deliveries_config

    @staticmethod
    def get_historical_folder_url(config_file_path: Optional[Path] = None) -> str:
        return DmsConfigLoader.get_distributor_deliveries_config(config_file_path)[
            'historical_folder_url'
        ]

    @staticmethod
    def get_current_folder_url(config_file_path: Optional[Path] = None) -> str:
        return DmsConfigLoader.get_distributor_deliveries_config(config_file_path)[
            'current_folder_url'
        ]
