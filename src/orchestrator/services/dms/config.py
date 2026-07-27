"""Configuration loading for DMS folder URLs and optional credentials."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, Optional

import yaml


class DmsConfigLoader:
    """Loads DMS configuration (folder URLs + optional auth) from YAML / env."""

    @staticmethod
    def _get_default_config_file_path() -> Path:
        current_file_directory = Path(__file__).parent.parent.parent
        return current_file_directory / "config" / "dms.yml"

    @staticmethod
    def resolve_config_path(config_file_path: Optional[Path] = None) -> Path:
        """Return DISTCORE_DMS_CONFIG when set, else default or explicit path."""
        if config_file_path is not None:
            return Path(config_file_path).expanduser().resolve()
        raw = os.environ.get("DISTCORE_DMS_CONFIG", "").strip()
        if raw:
            return Path(raw).expanduser().resolve()
        return DmsConfigLoader._get_default_config_file_path()

    @staticmethod
    def load_config(config_file_path: Optional[Path] = None) -> Dict[str, Any]:
        config_path = DmsConfigLoader.resolve_config_path(config_file_path)

        if not config_path.exists():
            raise FileNotFoundError(
                f"DMS configuration file not found: {config_path}\n"
                f"Please create the config file with folder URLs."
            )

        with open(config_path, "r", encoding="utf-8") as config_file:
            config = yaml.safe_load(config_file)

        if not config or "dms" not in config:
            raise ValueError("Invalid DMS configuration: 'dms' key not found")

        return config["dms"]

    @staticmethod
    def get_distributor_deliveries_config(
        config_file_path: Optional[Path] = None,
    ) -> Dict[str, str]:
        config = DmsConfigLoader.load_config(config_file_path)

        if "distributor_deliveries" not in config:
            raise ValueError(
                "Configuration key 'distributor_deliveries' not found in DMS configuration"
            )

        deliveries_config = config["distributor_deliveries"]
        required_keys = ("historical_folder_url", "current_folder_url")
        missing = [key for key in required_keys if key not in deliveries_config]
        if missing:
            raise ValueError(
                f"Missing DMS distributor_deliveries keys: {', '.join(missing)}"
            )

        return deliveries_config

    @staticmethod
    def get_historical_folder_url(config_file_path: Optional[Path] = None) -> str:
        return DmsConfigLoader.get_distributor_deliveries_config(config_file_path)[
            "historical_folder_url"
        ]

    @staticmethod
    def get_current_folder_url(config_file_path: Optional[Path] = None) -> str:
        return DmsConfigLoader.get_distributor_deliveries_config(config_file_path)[
            "current_folder_url"
        ]

    @staticmethod
    def get_auth_settings(config_file_path: Optional[Path] = None) -> Dict[str, Optional[str]]:
        """
        Resolve DMS auth settings.

        Precedence for username/password/auth mode:
        1. Environment: DISTCORE_DMS_USERNAME / DISTCORE_DMS_PASSWORD / DISTCORE_DMS_AUTH
        2. Values under the top-level ``dms`` key in dms.yml
        3. Defaults (auth mode ``auto``)
        """
        file_username: Optional[str] = None
        file_password: Optional[str] = None
        file_auth: Optional[str] = None

        try:
            config = DmsConfigLoader.load_config(config_file_path)
        except FileNotFoundError:
            config = {}

        if isinstance(config, dict):
            raw_user = config.get("username")
            raw_pass = config.get("password")
            raw_auth = config.get("auth")
            if isinstance(raw_user, str) and raw_user.strip():
                file_username = raw_user.strip()
            if isinstance(raw_pass, str) and raw_pass:
                file_password = raw_pass
            if isinstance(raw_auth, str) and raw_auth.strip():
                file_auth = raw_auth.strip().lower()

        env_username = os.environ.get("DISTCORE_DMS_USERNAME", "").strip() or None
        env_password = os.environ.get("DISTCORE_DMS_PASSWORD", "") or None
        if env_password is not None and not env_password:
            env_password = None
        env_auth = os.environ.get("DISTCORE_DMS_AUTH", "").strip().lower() or None

        return {
            "username": env_username or file_username,
            "password": env_password if env_password is not None else file_password,
            "auth": env_auth or file_auth or "auto",
        }
