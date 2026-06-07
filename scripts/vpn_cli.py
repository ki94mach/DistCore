"""Standalone helper to drive the Cisco AnyConnect VPN from the command line.

Usage:
    python scripts/vpn_cli.py status
    python scripts/vpn_cli.py connect
    python scripts/vpn_cli.py disconnect

Connection details come from src/orchestrator/config/vpn.yml.
The password is read from (in order): vpn.yml -> env var DISTCORE_VPN_PASSWORD
-> interactive prompt.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.orchestrator.services.vpn import VpnClient, VpnError
from src.orchestrator.ui.terminal_ui import (
    print_header,
    print_success,
    print_error,
    print_info,
    print_action,
)


def _client() -> VpnClient:
    return VpnClient(log_fn=print_info)


def cmd_status() -> int:
    client = _client()
    if client.is_connected():
        print_success(f"VPN is CONNECTED ({client.settings.host}).")
    else:
        print_info(f"VPN is DISCONNECTED ({client.settings.host}).")
    return 0


def cmd_connect() -> int:
    client = _client()
    print_action(f"Bringing up VPN to {client.settings.host}...")
    client.connect()
    print_success("VPN is up.")
    return 0


def cmd_disconnect() -> int:
    client = _client()
    client.disconnect()
    print_success("VPN is down.")
    return 0


COMMANDS = {
    'status': cmd_status,
    'state': cmd_status,
    'connect': cmd_connect,
    'up': cmd_connect,
    'disconnect': cmd_disconnect,
    'down': cmd_disconnect,
}


def main() -> int:
    print_header("AnyConnect VPN Control", )
    command = (sys.argv[1].lower() if len(sys.argv) > 1 else 'status')
    handler = COMMANDS.get(command)
    if handler is None:
        print_error(f"Unknown command '{command}'. "
                    f"Use one of: {', '.join(sorted(COMMANDS))}.")
        return 2
    try:
        return handler()
    except (VpnError, FileNotFoundError, OSError, ValueError) as exc:
        print_error(str(exc))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
