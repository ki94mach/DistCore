"""Interactive VPN pre-flight check for CLI tools.

CLI tools that reach SQL Server or DMS (both behind the corporate VPN) should
call ``ensure_vpn_connected()`` once at startup. It checks the tunnel and, if
it is down, asks the user whether to bring it up.

Design goals:
  * Never hard-crash the host tool. Any problem managing the VPN degrades to a
    warning and lets the tool continue (the underlying connection will surface
    a clear error if the network really is unreachable).
  * Do nothing surprising in non-interactive sessions (no TTY): warn and
    continue without connecting.
  * Smart teardown: when (and only when) this helper opens the tunnel, it
    registers an ``atexit`` hook to disconnect it again when the process ends.
    A tunnel that was already up (e.g. connected manually beforehand) is left
    untouched.
"""

import atexit
import sys
from typing import Callable, Optional

# Ensures we only register one teardown hook per process.
_DISCONNECT_REGISTERED = False


def _stdin_is_interactive() -> bool:
    try:
        return bool(sys.stdin) and sys.stdin.isatty()
    except Exception:
        return False


def _register_disconnect_on_exit(client, log: Callable[[str], None]) -> None:
    """Disconnect the VPN at interpreter exit (only the tunnel we opened)."""
    global _DISCONNECT_REGISTERED
    if _DISCONNECT_REGISTERED:
        return
    _DISCONNECT_REGISTERED = True

    def _teardown() -> None:
        try:
            if client.is_connected():
                log("[VPN] Disconnecting the tunnel this session opened...")
                client.disconnect()
        except Exception:
            pass

    atexit.register(_teardown)


def ensure_vpn_connected(
    *,
    interactive: bool = True,
    log_fn: Optional[Callable[[str], None]] = None,
    prompt_fn: Optional[Callable[[str], str]] = None,
    disconnect_on_exit: bool = True,
) -> bool:
    """Ensure the VPN is up, prompting the user to connect if it is not.

    Args:
        interactive: When False, never prompt (just check and warn).
        log_fn: Optional message sink (defaults to ``print``).
        prompt_fn: Optional input function (defaults to ``input``); useful for
            tests or custom UIs.
        disconnect_on_exit: When True (default), if this call opens the tunnel
            it is disconnected automatically when the process exits. A tunnel
            that was already connected is never torn down here.

    Returns:
        True if the VPN is connected (or could not be managed, so the tool
        should proceed); False if the VPN is down and the user declined to
        connect, or a connect attempt failed.
    """
    log = log_fn or (lambda message: print(message))

    try:
        from .client import VpnClient
        client = VpnClient(log_fn=log)
    except Exception as exc:
        # No config, not on Windows, vpncli.exe missing, etc. Don't block.
        log(f"[VPN] Pre-flight skipped (VPN automation unavailable: {exc}).")
        return True

    try:
        if client.is_connected():
            return True
    except Exception as exc:
        log(f"[VPN] Could not read VPN state ({exc}); continuing.")
        return True

    log(f"[VPN] Not connected. SQL Server and DMS hosts are behind "
        f"{client.settings.host}.")

    if not interactive or not _stdin_is_interactive():
        log("[VPN] Non-interactive session — continuing without connecting "
            "(connections may fail).")
        return False

    ask = prompt_fn or input
    try:
        answer = ask("[VPN] Connect to the VPN now? (Y/n): ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        answer = 'n'

    if answer in ('', 'y', 'yes'):
        try:
            client.connect()
            if disconnect_on_exit:
                _register_disconnect_on_exit(client, log)
            return True
        except Exception as exc:
            log(f"[VPN] Connect failed: {exc}")
            return False

    log("[VPN] Continuing without VPN — SQL/DMS connections may fail.")
    return False
