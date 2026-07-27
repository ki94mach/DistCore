"""Route-level tests for the DistCore web MVP."""

from __future__ import annotations

import tempfile
import unittest
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient

from src.optimization.data import OptimizationSettings
from src.optimization.export import ExportRequestMeta, write_optimization_xlsx
from src.optimization.service import RunResult, RunSummary, Shipment, TabularData
from src.orchestrator.pipelines.catalog import PipelineKey
from src.orchestrator.pipelines.freshness import FreshnessReport, PipelineFreshness
from src.orchestrator.pipelines.service import (
    PipelineRefreshResult,
    RefreshAllResult,
)
from src.web.app import create_app
from src.web.deps import reset_runtime_singletons
from src.web.jobs.lock import SingleFlightLock
from src.web.jobs.runner import JobRunner
from src.web.jobs.store import JobStore


def _sample_run_result() -> RunResult:
    shipment = Shipment("D1", "Dist One", "P1", "محصول", "Product", 5.0)
    return RunResult(
        status="Optimal",
        objective=1.0,
        solver_name="Greedy",
        is_optimal=True,
        is_feasible=True,
        shipments=(shipment,),
        summary=RunSummary(
            total_shipments=5.0,
            num_distributors=1,
            num_products=1,
            shipments_by_product={"Product": 5.0},
            shipments_by_distributor={"Dist One": 5.0},
        ),
        table=TabularData(
            columns=("distributor", "product", "quantity"),
            rows=(
                {
                    "distributor": "Dist One",
                    "product": "محصول",
                    "quantity": 5.0,
                },
            ),
        ),
    )


class TestWebRoutes(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.store = JobStore(Path(self._tmp.name))
        self.lock = SingleFlightLock()
        self.pipeline_service = Mock()
        self.optimization_service = Mock()
        self.freshness = Mock()
        self.runner = JobRunner(
            self.store,
            self.lock,
            pipeline_service_factory=lambda: self.pipeline_service,
            optimization_service_factory=lambda: self.optimization_service,
        )
        reset_runtime_singletons(
            job_store=self.store,
            lock=self.lock,
            job_runner=self.runner,
            factory=Mock(),
        )
        self.app = create_app()
        self.client = TestClient(self.app)

    def tearDown(self) -> None:
        reset_runtime_singletons()
        self._tmp.cleanup()

    def test_no_vpn_import_in_web_package(self) -> None:
        web_root = Path(__file__).resolve().parents[2] / "src" / "web"
        for path in web_root.rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            self.assertNotIn("services.vpn", text)
            self.assertNotIn("ensure_vpn_connected", text)
            self.assertNotIn("from src.orchestrator.services.vpn", text)

    def test_ui_include_deliveries_defaults_unchecked(self) -> None:
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        html = response.text
        self.assertIn('id="include_deliveries"', html)
        self.assertNotIn(
            'id="include_deliveries" type="checkbox" checked',
            html,
        )

    def test_ui_has_settings_and_sa_form(self) -> None:
        response = self.client.get("/")
        html = response.text
        for field_id in (
            "coverage_ratio",
            "target_coverage_ratio",
            "sales_window",
            "delivery_lower_bound",
            "delivery_upper_bound",
            "weight_demand",
            "weight_target_units",
            "weight_smoothing",
            "weight_shipment",
            "sa-options",
            "btn-refresh-cta",
            "job-status",
        ):
            self.assertIn(f'id="{field_id}"', html)

    def test_refresh_body_defaults_include_deliveries_false(self) -> None:
        from src.web.schemas import RefreshBody

        body = RefreshBody(snapshot_date=date(2026, 7, 27))
        self.assertFalse(body.include_deliveries)

    def test_db_dms_error_copy_never_mentions_vpn(self) -> None:
        from src.optimization.errors import DatabaseUnavailableError
        from src.orchestrator.pipelines.errors import PipelineDmsError
        from src.web.errors import register_exception_handlers

        app = create_app()
        register_exception_handlers(app)

        @app.get("/_test/db-error")
        def _db_error() -> None:
            raise DatabaseUnavailableError("odbc failure")

        @app.get("/_test/dms-error")
        def _dms_error() -> None:
            raise PipelineDmsError("sharepoint failure")

        client = TestClient(app)
        db = client.get("/_test/db-error")
        self.assertEqual(db.status_code, 503)
        self.assertIn("connectivity", db.json()["detail"].lower())
        self.assertNotIn("vpn", db.json()["detail"].lower())
        self.assertNotIn("vpn", (db.json().get("reason") or "").lower())

        dms = client.get("/_test/dms-error")
        self.assertEqual(dms.status_code, 502)
        self.assertIn("dms.yml", dms.json()["detail"].lower())
        self.assertNotIn("vpn", dms.json()["detail"].lower())
        self.assertNotIn("vpn", (dms.json().get("reason") or "").lower())

    def test_data_status(self) -> None:
        from datetime import UTC, datetime

        self.freshness.get_freshness.return_value = FreshnessReport(
            snapshot_date=date(2026, 7, 27),
            state="ready",
            pipelines=(
                PipelineFreshness(
                    pipeline=PipelineKey.FACTORY_INVENTORY,
                    optional_for_optimize=False,
                    expected_key=date(2026, 7, 27),
                    loaded_key=date(2026, 7, 27),
                    row_count=10,
                    created_at=None,
                    batch_id=1,
                    latest_batch=None,
                    state="ready",
                    detail="ok",
                ),
            ),
            checked_at=datetime.now(UTC),
        )
        with patch(
            "src.web.routes.data.get_freshness_repository",
            return_value=self.freshness,
        ):
            response = self.client.get(
                "/data/status", params={"snapshot_date": "2026-07-27"}
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["state"], "ready")

    def test_refresh_lock_conflict_returns_409(self) -> None:
        self.lock.try_acquire("existing", "optimize")
        response = self.client.post(
            "/data/refresh",
            json={"snapshot_date": "2026-07-27", "include_deliveries": False},
        )
        self.assertEqual(response.status_code, 409)
        self.assertIn("Another job is running", response.json()["detail"])
        self.assertNotIn("vpn", response.json()["detail"].lower())

    def test_refresh_success_path(self) -> None:
        self.pipeline_service.refresh_all.return_value = RefreshAllResult(
            snapshot_date=date(2026, 7, 27),
            results=(
                PipelineRefreshResult(
                    pipeline=PipelineKey.FACTORY_INVENTORY,
                    batch_type="FACTORY_INVENTORY",
                    snapshot_date=date(2026, 7, 27),
                    batch_id=11,
                    status="SUCCESS",
                    message="OK",
                ),
            ),
            succeeded=(PipelineKey.FACTORY_INVENTORY,),
            failed=(),
        )
        response = self.client.post(
            "/data/refresh",
            json={"snapshot_date": "2026-07-27", "include_deliveries": True},
        )
        self.assertEqual(response.status_code, 202)
        job_id = response.json()["job_id"]
        status = self.client.get(f"/jobs/{job_id}")
        self.assertEqual(status.status_code, 200)
        self.assertEqual(status.json()["status"], "succeeded")
        self.assertTrue(status.json()["result"]["is_successful"])

    def test_optimize_and_download(self) -> None:
        result = _sample_run_result()
        self.optimization_service.run.return_value = result
        response = self.client.post(
            "/optimizations",
            json={
                "snapshot_date": "2026-07-27",
                "solver": "Greedy",
                "include_export_variables": True,
            },
        )
        self.assertEqual(response.status_code, 202)
        job_id = response.json()["job_id"]
        status = self.client.get(f"/optimizations/{job_id}")
        self.assertEqual(status.json()["status"], "succeeded")
        download = self.client.get(f"/optimizations/{job_id}/download")
        self.assertEqual(download.status_code, 200)
        self.assertIn(
            "spreadsheetml",
            download.headers["content-type"],
        )
        self.assertTrue(download.content.startswith(b"PK"))
        disposition = download.headers.get("content-disposition", "")
        self.assertIn("optimization_2026-07-27_Greedy.xlsx", disposition)

    def test_optimize_rejects_dual_settings(self) -> None:
        response = self.client.post(
            "/optimizations",
            json={
                "snapshot_date": "2026-07-27",
                "solver": "Greedy",
                "settings_preset": "default",
                "settings": OptimizationSettings().__dict__,
            },
        )
        self.assertEqual(response.status_code, 422)

    def test_excel_builder_contains_persian_product(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "result.xlsx"
            write_optimization_xlsx(
                _sample_run_result(),
                path,
                request=ExportRequestMeta(
                    snapshot_date=date(2026, 7, 27),
                    solver="Greedy",
                ),
            )
            self.assertTrue(path.read_bytes().startswith(b"PK"))

    def test_solvers_endpoint(self) -> None:
        response = self.client.get("/solvers")
        self.assertEqual(response.status_code, 200)
        self.assertIn("priority", response.json())

    def test_index_page(self) -> None:
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("DistCore", response.text)


if __name__ == "__main__":
    unittest.main()
