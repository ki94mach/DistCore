"""Tests for web MVP env wiring helpers."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.web.deps import (
    get_connection_factory,
    get_job_store,
    reset_runtime_singletons,
    resolve_bind_host,
    resolve_bind_port,
    resolve_db_config_path,
    resolve_jobs_root,
)


class TestWebEnvWiring(unittest.TestCase):
    def tearDown(self) -> None:
        reset_runtime_singletons()

    def test_resolve_defaults(self) -> None:
        cleared = {
            "DISTCORE_DB_CONFIG": "",
            "DISTCORE_JOBS_DIR": "",
            "DISTCORE_HOST": "",
            "DISTCORE_PORT": "",
        }
        with patch.dict(os.environ, cleared, clear=False):
            # Empty strings should fall back to defaults.
            self.assertIsNone(resolve_db_config_path())
            self.assertEqual(
                resolve_jobs_root(),
                Path(__file__).resolve().parents[2] / "data" / "jobs",
            )
            self.assertEqual(resolve_bind_host(), "0.0.0.0")
            self.assertEqual(resolve_bind_port(), 8000)

    def test_resolve_overrides(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "custom_db.yml"
            jobs_path = Path(tmp) / "jobs"
            with patch.dict(
                os.environ,
                {
                    "DISTCORE_DB_CONFIG": str(db_path),
                    "DISTCORE_JOBS_DIR": str(jobs_path),
                    "DISTCORE_HOST": "127.0.0.1",
                    "DISTCORE_PORT": "9001",
                },
                clear=False,
            ):
                self.assertEqual(resolve_db_config_path(), db_path.resolve())
                self.assertEqual(resolve_jobs_root(), jobs_path.resolve())
                self.assertEqual(resolve_bind_host(), "127.0.0.1")
                self.assertEqual(resolve_bind_port(), 9001)

    def test_job_store_uses_env_jobs_dir(self) -> None:
        reset_runtime_singletons()
        with tempfile.TemporaryDirectory() as tmp:
            jobs_path = Path(tmp) / "env_jobs"
            with patch.dict(
                os.environ,
                {"DISTCORE_JOBS_DIR": str(jobs_path)},
                clear=False,
            ):
                store = get_job_store()
                self.assertEqual(store.root, jobs_path.resolve())

    def test_connection_factory_uses_env_config_path(self) -> None:
        reset_runtime_singletons()
        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "db.yml"
            with patch.dict(
                os.environ,
                {"DISTCORE_DB_CONFIG": str(config_path)},
                clear=False,
            ):
                with patch(
                    "src.web.deps.DBConnectionFactory.from_config_file"
                ) as from_file:
                    from_file.return_value = object()
                    factory = get_connection_factory()
                    from_file.assert_called_once_with(config_path.resolve())
                    self.assertIs(factory, from_file.return_value)


if __name__ == "__main__":
    unittest.main()
