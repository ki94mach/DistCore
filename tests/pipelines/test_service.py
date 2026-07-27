"""Tests for pipeline orchestration service and CLI adapter wiring."""

from __future__ import annotations

import importlib.util
import sys
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import Mock, patch

import pyodbc

from src.orchestrator.pipelines.catalog import PipelineKey
from src.orchestrator.pipelines.errors import (
    InvalidPipelineRequestError,
    PipelineDatabaseError,
    PipelineDmsError,
    PipelineExecutionError,
)
from src.orchestrator.pipelines.service import (
    PipelineService,
    RefreshAllRequest,
    RefreshRequest,
)


def _pipeline_with_batch(batch_id: int = 123):
    pipeline = Mock()
    pipeline.batch_id = batch_id
    pipeline.run.return_value = None
    return pipeline


class TestPipelineService(unittest.TestCase):
    def test_refresh_one_uses_runner_and_returns_batch(self) -> None:
        runner = Mock(return_value=_pipeline_with_batch(501))
        service = PipelineService(
            Mock(),
            pipeline_factories={PipelineKey.FACTORY_INVENTORY: runner},
        )
        result = service.refresh_one(
            RefreshRequest(
                pipeline=PipelineKey.FACTORY_INVENTORY,
                snapshot_date=date(2026, 7, 27),
            )
        )
        self.assertEqual(result.status, "SUCCESS")
        self.assertEqual(result.batch_id, 501)
        kwargs = runner.call_args.kwargs
        self.assertEqual(kwargs["triggered_by"], "WEB_UI")
        self.assertEqual(kwargs["database_type"], "prod")
        self.assertIsNone(kwargs["log_fn"])

    def test_refresh_all_keeps_catalog_order_and_continue_on_failure(self) -> None:
        calls: list[PipelineKey] = []

        def make_runner(key: PipelineKey, fail: bool = False):
            def _runner(**_kwargs):
                calls.append(key)
                pipeline = _pipeline_with_batch(10 + len(calls))
                if fail:
                    pipeline.run.side_effect = RuntimeError("boom")
                return pipeline

            return _runner

        service = PipelineService(
            Mock(),
            pipeline_factories={
                PipelineKey.FACTORY_INVENTORY: make_runner(PipelineKey.FACTORY_INVENTORY),
                PipelineKey.DISTRIBUTOR_INVENTORY: make_runner(
                    PipelineKey.DISTRIBUTOR_INVENTORY
                ),
                PipelineKey.SALES: make_runner(PipelineKey.SALES, fail=True),
                PipelineKey.TARGET: make_runner(PipelineKey.TARGET),
                PipelineKey.DISTRIBUTOR_DELIVERIES: make_runner(
                    PipelineKey.DISTRIBUTOR_DELIVERIES
                ),
            },
        )
        result = service.refresh_all(
            RefreshAllRequest(snapshot_date=date(2026, 7, 27), include_deliveries=False)
        )
        self.assertEqual(
            calls,
            [
                PipelineKey.FACTORY_INVENTORY,
                PipelineKey.DISTRIBUTOR_INVENTORY,
                PipelineKey.SALES,
                PipelineKey.TARGET,
            ],
        )
        self.assertIn(PipelineKey.SALES, result.failed)
        self.assertNotIn(PipelineKey.DISTRIBUTOR_DELIVERIES, [r.pipeline for r in result.results])

    def test_typed_error_translation(self) -> None:
        failing_db = Mock()
        failing_db.return_value = _pipeline_with_batch()
        failing_db.return_value.run.side_effect = pyodbc.Error("offline")
        service = PipelineService(
            Mock(),
            pipeline_factories={PipelineKey.FACTORY_INVENTORY: failing_db},
        )
        with self.assertRaises(PipelineDatabaseError):
            service.refresh_one(
                RefreshRequest(PipelineKey.FACTORY_INVENTORY, date(2026, 7, 27))
            )

        failing_dms = Mock()
        failing_dms.return_value = _pipeline_with_batch()
        failing_dms.return_value.run.side_effect = FileNotFoundError("dms")
        deliveries = PipelineService(
            Mock(),
            pipeline_factories={PipelineKey.DISTRIBUTOR_DELIVERIES: failing_dms},
        )
        with self.assertRaises(PipelineDmsError):
            deliveries.refresh_one(
                RefreshRequest(PipelineKey.DISTRIBUTOR_DELIVERIES, date(2026, 7, 27))
            )

        failing_exec = Mock()
        failing_exec.return_value = _pipeline_with_batch()
        failing_exec.return_value.run.side_effect = ValueError("bad")
        generic = PipelineService(
            Mock(),
            pipeline_factories={PipelineKey.TARGET: failing_exec},
        )
        with self.assertRaises(PipelineExecutionError):
            generic.refresh_one(RefreshRequest(PipelineKey.TARGET, date(2026, 7, 27)))

    def test_invalid_request(self) -> None:
        service = PipelineService(Mock())
        with self.assertRaises(InvalidPipelineRequestError):
            service.refresh_one(RefreshRequest("unknown", date(2026, 7, 27)))  # type: ignore[arg-type]


def _load_cli_module():
    project_root = Path(__file__).resolve().parents[2]
    path = project_root / "scripts" / "pipeline_cli.py"
    spec = importlib.util.spec_from_file_location("pipeline_cli_for_test", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class TestPipelineCliAdapter(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.cli = _load_cli_module()

    def test_full_pipeline_uses_service_request(self) -> None:
        service_instance = Mock()
        service_instance.refresh_one.return_value = Mock(batch_id=999)
        pipeline_info = {
            "key": PipelineKey.FACTORY_INVENTORY,
            "name": "Factory Inventory",
            "batch_type": "FACTORY_INVENTORY",
            "class": Mock(),
        }
        with (
            patch.object(self.cli, "configure_sql_options", return_value={"snapshot_date": date(2026, 7, 27)}),
            patch.object(self.cli, "configure_deliveries_load", return_value={"snapshot_date": date(2026, 7, 27)}),
            patch.object(self.cli, "print_run_plan"),
            patch.object(self.cli, "print_run_footer"),
            patch.object(self.cli, "PipelineService", return_value=service_instance),
        ):
            self.cli.run_full_pipeline(pipeline_info)
        request = service_instance.refresh_one.call_args.args[0]
        self.assertEqual(request.triggered_by, "MANUAL_TEST")
        self.assertEqual(request.snapshot_date, date(2026, 7, 27))

    def test_main_keeps_vpn_preflight(self) -> None:
        with (
            patch.object(self.cli, "ensure_vpn_connected") as vpn,
            patch.object(self.cli, "select_pipeline", return_value=None),
        ):
            self.cli.main()
        vpn.assert_called_once()


if __name__ == "__main__":
    unittest.main()
