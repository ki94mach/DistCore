"""Unit tests for DMS auth resolution and config loading."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from src.orchestrator.services.dms.client import resolve_dms_auth
from src.orchestrator.services.dms.config import DmsConfigLoader


class DmsAuthSettingsTests(unittest.TestCase):
    def setUp(self) -> None:
        self._env_keys = (
            "DISTCORE_DMS_CONFIG",
            "DISTCORE_DMS_USERNAME",
            "DISTCORE_DMS_PASSWORD",
            "DISTCORE_DMS_AUTH",
        )
        self._saved = {key: os.environ.get(key) for key in self._env_keys}
        for key in self._env_keys:
            os.environ.pop(key, None)

    def tearDown(self) -> None:
        for key, value in self._saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def _write_config(self, body: str) -> Path:
        handle = tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".yml",
            delete=False,
            encoding="utf-8",
        )
        with handle:
            handle.write(body)
        self.addCleanup(lambda: Path(handle.name).unlink(missing_ok=True))
        return Path(handle.name)

    def test_env_overrides_file_credentials(self) -> None:
        path = self._write_config(
            """
dms:
  auth: basic
  username: file-user
  password: file-pass
  distributor_deliveries:
    historical_folder_url: https://example/h
    current_folder_url: https://example/c
"""
        )
        os.environ["DISTCORE_DMS_USERNAME"] = "env-user"
        os.environ["DISTCORE_DMS_PASSWORD"] = "env-pass"
        os.environ["DISTCORE_DMS_AUTH"] = "ntlm"

        settings = DmsConfigLoader.get_auth_settings(path)
        self.assertEqual(settings["username"], "env-user")
        self.assertEqual(settings["password"], "env-pass")
        self.assertEqual(settings["auth"], "ntlm")

    def test_file_credentials_used_when_env_absent(self) -> None:
        path = self._write_config(
            """
dms:
  username: file-user
  password: file-pass
  distributor_deliveries:
    historical_folder_url: https://example/h
    current_folder_url: https://example/c
"""
        )
        settings = DmsConfigLoader.get_auth_settings(path)
        self.assertEqual(settings["username"], "file-user")
        self.assertEqual(settings["password"], "file-pass")
        self.assertEqual(settings["auth"], "auto")


class ResolveDmsAuthTests(unittest.TestCase):
    def setUp(self) -> None:
        self._env_keys = (
            "DISTCORE_DMS_CONFIG",
            "DISTCORE_DMS_USERNAME",
            "DISTCORE_DMS_PASSWORD",
            "DISTCORE_DMS_AUTH",
        )
        self._saved = {key: os.environ.get(key) for key in self._env_keys}
        for key in self._env_keys:
            os.environ.pop(key, None)

    def tearDown(self) -> None:
        for key, value in self._saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    @patch("src.orchestrator.services.dms.client._get_ntlm_auth")
    def test_auto_uses_ntlm_when_credentials_present(
        self, ntlm_mock: MagicMock
    ) -> None:
        ntlm_mock.return_value = "ntlm-auth"
        auth = resolve_dms_auth(
            username="user@example.com",
            password="secret",
            auth_mode="auto",
        )
        self.assertEqual(auth, "ntlm-auth")
        ntlm_mock.assert_called_once_with("user@example.com", "secret")

    @patch("src.orchestrator.services.dms.client.sys")
    def test_auto_on_linux_without_credentials_raises(
        self, sys_mock: MagicMock
    ) -> None:
        sys_mock.platform = "linux"
        with self.assertRaises(OSError) as ctx:
            resolve_dms_auth(auth_mode="auto")
        self.assertIn("Linux", str(ctx.exception))

    @patch("src.orchestrator.services.dms.client._get_sspi_auth")
    @patch("src.orchestrator.services.dms.client.sys")
    def test_auto_on_windows_without_credentials_uses_sspi(
        self, sys_mock: MagicMock, sspi_mock: MagicMock
    ) -> None:
        sys_mock.platform = "win32"
        sspi_mock.return_value = "sspi-auth"
        auth = resolve_dms_auth(auth_mode="auto")
        self.assertEqual(auth, "sspi-auth")
        sspi_mock.assert_called_once_with()

    @patch("src.orchestrator.services.dms.client._get_basic_auth")
    def test_basic_mode(self, basic_mock: MagicMock) -> None:
        basic_mock.return_value = "basic-auth"
        auth = resolve_dms_auth(
            username="u",
            password="p",
            auth_mode="basic",
        )
        self.assertEqual(auth, "basic-auth")
        basic_mock.assert_called_once_with("u", "p")

    def test_invalid_mode_raises(self) -> None:
        with self.assertRaises(ValueError):
            resolve_dms_auth(auth_mode="kerberos")


if __name__ == "__main__":
    unittest.main()
