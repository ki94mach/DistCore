"""Configuration loading for Cisco AnyConnect VPN automation."""

import os
import yaml
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


DEFAULT_VPNCLI_PATHS = (
    r"C:\Program Files (x86)\Cisco\Cisco AnyConnect Secure Mobility Client\vpncli.exe",
    r"C:\Program Files\Cisco\Cisco AnyConnect Secure Mobility Client\vpncli.exe",
)

# Default ordered responses sent to the interactive `connect` prompts.
# Placeholders {group}, {username}, {password} are substituted at runtime.
DEFAULT_PROMPT_RESPONSES = ("{group}", "{username}", "{password}")

# Environment variable consulted when no password is provided explicitly.
PASSWORD_ENV_VAR = "DISTCORE_VPN_PASSWORD"


@dataclass
class VpnSettings:
    """Resolved settings for driving the AnyConnect CLI."""

    host: str
    group: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = None
    vpncli_path: Optional[str] = None
    close_gui_before_connect: bool = True
    connect_timeout_seconds: int = 60
    prompt_responses: List[str] = field(
        default_factory=lambda: list(DEFAULT_PROMPT_RESPONSES)
    )

    def resolve_vpncli_path(self) -> str:
        """Return a usable path to vpncli.exe, validating it exists."""
        candidates: List[str] = []
        if self.vpncli_path:
            candidates.append(self.vpncli_path)
        candidates.extend(DEFAULT_VPNCLI_PATHS)

        for candidate in candidates:
            if candidate and Path(candidate).is_file():
                return candidate

        raise FileNotFoundError(
            "Could not locate vpncli.exe. Set 'vpncli_path' in vpn.yml. "
            f"Looked in: {', '.join(candidates)}"
        )

    def resolve_password(self) -> Optional[str]:
        """Password from config, else the environment variable (if set)."""
        if self.password:
            return self.password
        return os.environ.get(PASSWORD_ENV_VAR) or None


class VpnConfigLoader:
    """Loads Cisco AnyConnect VPN configuration from a YAML config file."""

    @staticmethod
    def _get_default_config_file_path() -> Path:
        current_file_directory = Path(__file__).parent.parent.parent
        return current_file_directory / 'config' / 'vpn.yml'

    @staticmethod
    def load_config(config_file_path: Optional[Path] = None) -> Dict[str, Any]:
        config_path = config_file_path or VpnConfigLoader._get_default_config_file_path()

        if not config_path.exists():
            raise FileNotFoundError(
                f"VPN configuration file not found: {config_path}\n"
                f"Create it with at least a 'vpn.host' entry."
            )

        with open(config_path, 'r', encoding='utf-8') as config_file:
            config = yaml.safe_load(config_file)

        if not config or 'vpn' not in config:
            raise ValueError("Invalid VPN configuration: 'vpn' key not found")

        return config['vpn']

    @staticmethod
    def load_settings(config_file_path: Optional[Path] = None) -> VpnSettings:
        """Load YAML config into a validated VpnSettings object."""
        raw = VpnConfigLoader.load_config(config_file_path)

        host = raw.get('host')
        if not host:
            raise ValueError("VPN configuration is missing required key 'host'")

        prompt_responses = raw.get('prompt_responses')
        if not prompt_responses:
            prompt_responses = list(DEFAULT_PROMPT_RESPONSES)

        return VpnSettings(
            host=host,
            group=raw.get('group'),
            username=raw.get('username'),
            password=raw.get('password'),
            vpncli_path=raw.get('vpncli_path'),
            close_gui_before_connect=bool(raw.get('close_gui_before_connect', True)),
            connect_timeout_seconds=int(raw.get('connect_timeout_seconds', 60)),
            prompt_responses=list(prompt_responses),
        )
