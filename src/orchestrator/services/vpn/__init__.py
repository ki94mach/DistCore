"""VPN service: automate the Cisco AnyConnect tunnel via vpncli.exe."""

from .client import VpnClient, VpnError
from .config import VpnConfigLoader, VpnSettings
from .preflight import ensure_vpn_connected

__all__ = [
    'VpnClient',
    'VpnError',
    'VpnConfigLoader',
    'VpnSettings',
    'ensure_vpn_connected',
]
