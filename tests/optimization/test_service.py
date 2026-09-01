"""Tests for the non-interactive optimization service and CLI adapter."""

from __future__ import annotations

import csv
import importlib.util
import json
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from src.optimization.constraints import (
    DeliveryHistoryConstraint,
    DeliverySmoothingConstraint,
    DemandCoverageConstraint,
    FactorySupplyConstraint,
    ProductTargetUnitsConstraint,
    ShipmentMinimizationConstraint,
)
from src.optimization.data import OptimizationData, OptimizationSettings
from src.optimization.export import SHIPMENTS_BASE_COLUMNS
from src.optimization.errors import (
    DatabaseUnavailableError,
    InvalidRunRequestError,
    MissingSnapshotError,
    SolverUnavailableError,
)
from src.optimization.lp import Variable
from src.optimization.service import (
    OptimizationService,
    RunRequest,
    RunResult,
    RunSummary,
    Shipment,
    TabularData,
)
from src.optimization.solvers.base import Solution


def _sample_data(settings: OptimizationSettings | None = None) -> OptimizationData:
    return OptimizationData(
        distributors=["D1"],
        products=["P1"],
        factory_inventory={"P1": 100.0},
        distributor_inventory={("D1", "P1"): 4.0},
        sales_ma_3={("D1", "P1"): 20.0},
        sales_ma_6={("D1", "P1"): 18.0},
        sales_mtd={("D1", "P1"): 5.0},
        target_units={"P1": 50.0},
        settings=settings or OptimizationSettings(),
        delivery_ma_6={("D1", "P1"): 9.0},
        has_delivery_last_6m={("D1", "P1"): True},
        distributor_names={"D1": "Distributor One"},
        product_names={"P1": "محصول یک"},
        product_names_en={"P1": "Product One"},
    )


class ServiceHarness:
    def __init__(
        self,
        *,
        data: OptimizationData | None = None,
        status: str = "Optimal",
        objective: float | None = 12.345,
        quantity: float = 7.126,
    ) -> None:
        self.data = data or _sample_data()
        self.variable = Variable("x_D1_P1")
        self.loader = Mock()
        self.loader.load_optimization_data.return_value = self.data
        self.loader_factory = Mock(return_value=self.loader)
        self.build_result = SimpleNamespace(
            model=object(),
            decision_variables={("D1", "P1"): self.variable},
            slack_variables=[],
        )
        self.builder = Mock()
        self.builder.build.return_value = self.build_result
        self.builder_factory = Mock(return_value=self.builder)
        self.solve_fn = Mock(
            return_value=Solution(
                status=status,
                objective_value=objective,
                variable_values={self.variable: quantity},
                is_optimal=status == "Optimal",
                solver_name="Greedy",
            )
        )
        self.service = OptimizationService(
            Mock(),
            loader_factory=self.loader_factory,
            builder_factory=self.builder_factory,
            solve_fn=self.solve_fn,
        )


class TestOptimizationService(unittest.TestCase):
    def test_run_forwards_inputs_and_uses_exact_constraint_set(self) -> None:
        harness = ServiceHarness()
        settings = OptimizationSettings(coverage_ratio=2.0)
        options = {"Greedy": {"unused_test_option": 1}}
        request = RunRequest(
            snapshot_date=date(2026, 7, 27),
            snapshot_month=date(2026, 7, 1),
            solver="Greedy",
            settings=settings,
            solver_options=options,
        )

        result = harness.service.run(request)

        harness.loader_factory.assert_called_once_with(
            sql_executor=harness.service._sql_executor,
            database_type="prod",
        )
        harness.loader.load_optimization_data.assert_called_once_with(
            snapshot_date=request.snapshot_date,
            snapshot_month=request.snapshot_month,
            settings=settings,
        )
        constraints = harness.builder_factory.call_args.args[0]
        self.assertEqual(
            [type(item) for item in constraints],
            [
                FactorySupplyConstraint,
                DeliveryHistoryConstraint,
                DeliverySmoothingConstraint,
                DemandCoverageConstraint,
                ProductTargetUnitsConstraint,
                ShipmentMinimizationConstraint,
            ],
        )
        harness.builder.build.assert_called_once_with(
            harness.data, settings_override=settings
        )
        solve_call = harness.solve_fn.call_args
        self.assertEqual(solve_call.kwargs["method"], "Greedy")
        self.assertIs(solve_call.kwargs["data"], harness.data)
        self.assertEqual(solve_call.kwargs["solver_options"], options)
        self.assertEqual(result.status, "Optimal")

    def test_request_settings_resolution(self) -> None:
        default_harness = ServiceHarness()
        default_harness.service.run(
            RunRequest(snapshot_date=date(2026, 7, 27), solver="Greedy")
        )
        default_settings = (
            default_harness.loader.load_optimization_data.call_args.kwargs["settings"]
        )
        self.assertEqual(default_settings, OptimizationSettings())

        preset_harness = ServiceHarness()
        preset_harness.service.run(
            RunRequest(
                snapshot_date=date(2026, 7, 27),
                solver="Greedy",
                settings_preset="focus_demand",
            )
        )
        preset_settings = (
            preset_harness.loader.load_optimization_data.call_args.kwargs["settings"]
        )
        self.assertNotEqual(preset_settings, OptimizationSettings())

    def test_rejects_conflicting_or_unknown_settings(self) -> None:
        harness = ServiceHarness()
        with self.assertRaises(InvalidRunRequestError):
            harness.service.run(
                RunRequest(
                    snapshot_date=date(2026, 7, 27),
                    solver="Greedy",
                    settings=OptimizationSettings(),
                    settings_preset="default",
                )
            )
        with self.assertRaises(InvalidRunRequestError):
            harness.service.run(
                RunRequest(
                    snapshot_date=date(2026, 7, 27),
                    solver="Greedy",
                    settings_preset="does-not-exist",
                )
            )

    def test_formats_shipments_summaries_and_detailed_table(self) -> None:
        harness = ServiceHarness()
        result = harness.service.run(
            RunRequest(
                snapshot_date=date(2026, 7, 27),
                solver="Greedy",
                include_export_variables=True,
            )
        )

        self.assertEqual(result.objective, 12.35)
        self.assertEqual(result.shipments[0].quantity, 7.13)
        self.assertEqual(result.summary.total_shipments, 7.13)
        self.assertEqual(result.summary.shipments_by_product, {"Product One": 7.13})
        self.assertEqual(
            result.summary.shipments_by_distributor, {"Distributor One": 7.13}
        )
        self.assertEqual(result.table.columns[:3], SHIPMENTS_BASE_COLUMNS)
        self.assertIn("explanation", result.table.columns)
        self.assertIn("factory_supply_remaining", result.table.columns)
        row = result.table.rows[0]
        self.assertEqual(row["product"], "محصول یک")
        self.assertEqual(row["coverage_demand"], 15.0)
        self.assertEqual(row["factory_supply"], 100.0)
        self.assertEqual(row["demand_coverage_required"], 22.5)
        self.assertIn("explanation", row)
        self.assertEqual(
            result.to_dict()["shipments"][0]["product"], "Product One"
        )

    def test_basic_table_and_name_fallback(self) -> None:
        data = _sample_data()
        data = OptimizationData(
            **{
                **data.__dict__,
                "distributor_names": {},
                "product_names": {},
                "product_names_en": {},
            }
        )
        result = ServiceHarness(data=data).service.run(
            RunRequest(snapshot_date=date(2026, 7, 27), solver="Greedy")
        )
        self.assertEqual(
            result.table.columns, ("distributor", "product", "quantity")
        )
        self.assertEqual(result.table.rows[0]["distributor"], "D1")
        self.assertEqual(result.table.rows[0]["product"], "P1")

    def test_propagates_solution_feasibility_states(self) -> None:
        for status, feasible, optimal in (
            ("Optimal", True, True),
            ("Feasible", True, False),
            ("Infeasible", False, False),
        ):
            with self.subTest(status=status):
                result = ServiceHarness(status=status).service.run(
                    RunRequest(snapshot_date=date(2026, 7, 27), solver="Greedy")
                )
                self.assertEqual(result.is_feasible, feasible)
                self.assertEqual(result.is_optimal, optimal)

    def test_translates_expected_failures(self) -> None:
        missing = ServiceHarness()
        missing.loader.load_optimization_data.side_effect = ValueError("missing rows")
        with self.assertRaises(MissingSnapshotError):
            missing.service.run(
                RunRequest(snapshot_date=date(2026, 7, 27), solver="Greedy")
            )

        database = ServiceHarness()
        database.loader.load_optimization_data.side_effect = ConnectionError("offline")
        with self.assertRaises(DatabaseUnavailableError):
            database.service.run(
                RunRequest(snapshot_date=date(2026, 7, 27), solver="Greedy")
            )

        with self.assertRaises(SolverUnavailableError):
            ServiceHarness().service.run(
                RunRequest(
                    snapshot_date=date(2026, 7, 27),
                    solver="NotRegistered",
                )
            )

    def test_service_source_has_no_vpn_dependency(self) -> None:
        service_path = (
            Path(__file__).resolve().parents[2]
            / "src"
            / "optimization"
            / "service.py"
        )
        self.assertNotIn("services.vpn", service_path.read_text(encoding="utf-8"))


def _load_cli_module():
    project_root = Path(__file__).resolve().parents[2]
    path = project_root / "scripts" / "optimization_cli.py"
    spec = importlib.util.spec_from_file_location("optimization_cli_for_test", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _sample_result() -> RunResult:
    shipment = Shipment("D1", "Distributor One", "P1", "محصول یک", "Product One", 7.0)
    return RunResult(
        status="Optimal",
        objective=2.0,
        solver_name="Greedy",
        is_optimal=True,
        is_feasible=True,
        shipments=(shipment,),
        summary=RunSummary(
            total_shipments=7.0,
            num_distributors=1,
            num_products=1,
            shipments_by_product={"Product One": 7.0},
            shipments_by_distributor={"Distributor One": 7.0},
        ),
        table=TabularData(
            columns=("distributor", "product", "quantity"),
            rows=(
                {
                    "distributor": "Distributor One",
                    "product": "محصول یک",
                    "quantity": 7.0,
                },
            ),
        ),
    )


class TestOptimizationCliAdapter(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.cli = _load_cli_module()

    def test_run_maps_cli_config_to_service_request(self) -> None:
        result = _sample_result()
        service = Mock()
        service.run.return_value = result
        settings = OptimizationSettings()
        config = {
            "snapshot_date": date(2026, 7, 27),
            "snapshot_month": None,
            "database_type": "prod",
            "config_path": None,
            "settings": settings,
            "solver": "Greedy",
            "solver_options": {"Greedy": {}},
            "output_file": None,
            "csv_file": None,
            "csv_include_variables": True,
        }

        with (
            patch.object(self.cli, "initialize_database", return_value=Mock()),
            patch.object(self.cli, "OptimizationService", return_value=service),
        ):
            self.assertTrue(self.cli.run_optimization(config))

        request = service.run.call_args.args[0]
        self.assertEqual(request.snapshot_date, config["snapshot_date"])
        self.assertIs(request.settings, settings)
        self.assertEqual(request.solver, "Greedy")
        self.assertEqual(request.solver_options, {"Greedy": {}})
        self.assertTrue(request.include_export_variables)

    def test_json_and_csv_serialization_preserve_cli_shapes(self) -> None:
        result = _sample_result()
        with tempfile.TemporaryDirectory() as temp_dir:
            json_path = Path(temp_dir) / "result.json"
            csv_path = Path(temp_dir) / "result.csv"
            with patch.object(self.cli, "print_success"):
                self.cli.save_results(result, str(json_path))
                self.cli.save_results_csv(result, str(csv_path))

            payload = json.loads(json_path.read_text())
            self.assertEqual(payload["objective_value"], 2.0)
            self.assertEqual(payload["shipments"][0]["product"], "Product One")
            raw_csv = csv_path.read_bytes()
            self.assertTrue(raw_csv.startswith(b"\xef\xbb\xbf"))
            with csv_path.open(encoding="utf-8-sig", newline="") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(rows[0]["product"], "محصول یک")


if __name__ == "__main__":
    unittest.main()
