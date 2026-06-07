"""Cisco AnyConnect VPN client wrapping the vpncli.exe command-line tool.

This lets the pipeline bring up the corporate VPN tunnel (the one normally
opened with the AnyConnect GUI) so that internal SQL Server and DMS hosts
become reachable, without anyone clicking the GUI.

Notes / gotchas handled here:
  * The AnyConnect GUI (vpnui.exe) holds the agent connection; while it runs,
    a CLI login silently fails. We optionally close it before connecting.
  * vpncli reads credentials interactively. We drive it in script mode
    (`vpncli.exe -s`) and feed an ordered response sequence on stdin.
  * Prompt order varies per deployment (group/cert/banner). The sequence is
    configurable via `prompt_responses` in vpn.yml.
"""

import getpass
import subprocess
import sys
import time
from typing import Callable, List, Optional

from .config import VpnConfigLoader, VpnSettings


def _default_logger(message: str) -> None:
    print(message)


class VpnError(RuntimeError):
    """Raised when a VPN connect/disconnect operation fails."""


class VpnClient:
    """Thin automation wrapper around Cisco AnyConnect's vpncli.exe."""

    def __init__(
        self,
        settings: Optional[VpnSettings] = None,
        log_fn: Optional[Callable[[str], None]] = None,
    ):
        if sys.platform != 'win32':
            raise OSError(
                "VpnClient drives the Windows AnyConnect client (vpncli.exe) "
                "and only runs on Windows."
            )
        self._settings = settings or VpnConfigLoader.load_settings()
        self._log = log_fn or _default_logger
        self._vpncli_path = self._settings.resolve_vpncli_path()

    @property
    def settings(self) -> VpnSettings:
        return self._settings

    def _run_cli(
        self,
        args: List[str],
        stdin_text: Optional[str] = None,
        timeout: Optional[int] = None,
    ) -> subprocess.CompletedProcess:
        return subprocess.run(
            [self._vpncli_path, *args],
            input=stdin_text,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )

    def is_connected(self) -> bool:
        """Return True if AnyConnect reports an established tunnel."""
        try:
            result = self._run_cli(['state'], timeout=20)
        except subprocess.TimeoutExpired:
            return False
        output = (result.stdout or '') + (result.stderr or '')
        for line in output.splitlines():
            stripped = line.strip().lower()
            if stripped.startswith('>>'):
                stripped = stripped[2:].strip()
            if stripped.startswith('state:'):
                state = stripped.split(':', 1)[1].strip()
                return state == 'connected'
        return False

    def _close_gui(self) -> None:
        """Close the AnyConnect GUI so the CLI can drive the agent."""
        try:
            subprocess.run(
                ['taskkill', '/IM', 'vpnui.exe', '/F'],
                capture_output=True,
                text=True,
                check=False,
            )
        except Exception:
            pass

    def _build_stdin(self, password: str) -> str:
        substitutions = {
            'group': self._settings.group or '',
            'username': self._settings.username or '',
            'password': password,
        }
        lines = [f"connect {self._settings.host}"]
        for template in self._settings.prompt_responses:
            lines.append(template.format(**substitutions))
        # Trailing newline matters: vpncli needs the final prompt terminated.
        return "\n".join(lines) + "\n"

    def connect(self, password: Optional[str] = None) -> None:
        """Establish the VPN tunnel. No-op if already connected.

        Password resolution order: explicit arg -> vpn.yml -> env var ->
        interactive prompt.
        """
        if self.is_connected():
            self._log("VPN already connected.")
            return

        resolved_password = (
            password
            or self._settings.resolve_password()
            or self._prompt_password()
        )

        if self._settings.close_gui_before_connect:
            self._log("Closing AnyConnect GUI (vpnui.exe) if running...")
            self._close_gui()
            time.sleep(1)

        self._log(f"Connecting to {self._settings.host} as "
                  f"{self._settings.username or '<prompted>'}...")

        stdin_text = self._build_stdin(resolved_password)
        try:
            result = self._run_cli(
                ['-s'],
                stdin_text=stdin_text,
                timeout=self._settings.connect_timeout_seconds,
            )
        except subprocess.TimeoutExpired as exc:
            raise VpnError(
                f"VPN connect timed out after "
                f"{self._settings.connect_timeout_seconds}s."
            ) from exc

        if self._output_indicates_failure(result):
            raise VpnError(self._format_failure(result))

        # The CLI may return before the tunnel is fully up; poll state.
        if not self._wait_until_connected():
            raise VpnError(
                "vpncli finished but the tunnel is not in 'Connected' state.\n"
                + self._format_failure(result)
            )

        self._log("VPN connected.")

    def disconnect(self) -> None:
        """Tear down the VPN tunnel (safe to call when already down)."""
        if not self.is_connected():
            self._log("VPN already disconnected.")
            return
        self._log("Disconnecting VPN...")
        self._run_cli(['disconnect'], timeout=30)
        self._log("VPN disconnected.")

    def _prompt_password(self) -> str:
        if not sys.stdin or not sys.stdin.isatty():
            raise VpnError(
                "No VPN password available. Set it in vpn.yml, export "
                "DISTCORE_VPN_PASSWORD, or run interactively."
            )
        pwd = getpass.getpass(
            f"AnyConnect password for {self._settings.username or self._settings.host}: "
        )
        if not pwd:
            raise VpnError("Empty password provided.")
        return pwd

    def _wait_until_connected(self) -> bool:
        deadline = time.monotonic() + min(self._settings.connect_timeout_seconds, 30)
        while time.monotonic() < deadline:
            if self.is_connected():
                return True
            time.sleep(2)
        return self.is_connected()

    @staticmethod
    def _output_indicates_failure(result: subprocess.CompletedProcess) -> bool:
        output = ((result.stdout or '') + (result.stderr or '')).lower()
        failure_markers = (
            'login failed',
            'authentication failed',
            'connect attempt has failed',
            'no valid certificates',
            'unable to contact',
            'invalid host',
        )
        return any(marker in output for marker in failure_markers)

    @staticmethod
    def _format_failure(result: subprocess.CompletedProcess) -> str:
        output = ((result.stdout or '') + (result.stderr or '')).strip()
        relevant = [
            line.strip() for line in output.splitlines()
            if line.strip() and ('>>' in line or 'error' in line.lower()
                                 or 'fail' in line.lower())
        ]
        detail = "\n".join(relevant[-8:]) if relevant else output[-600:]
        return f"VPN connect failed:\n{detail}"

    def __enter__(self) -> "VpnClient":
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.disconnect()
