"""Tests for optimization Excel export."""

from __future__ import annotations

import tempfile
import unittest
from datetime import date
from pathlib import Path

from openpyxl import load_workbook

from src.optimization.data import OptimizationSettings
from src.optimization.export import (
    ExportRequestMeta,
    SHIPMENTS_BASE_COLUMNS,
    SHIPMENTS_DETAIL_COLUMNS,
    SHIPMENTS_TABLE_COLUMNS,
    build_optimization_workbook,
    download_filename,
    write_optimization_xlsx,
)
from src.optimization.explain import shipment_column_label
from src.optimization.service import RunResult, RunSummary, Shipment, TabularData


def _fake_result(*, include_variables: bool = False) -> RunResult:
    columns = list(SHIPMENTS_BASE_COLUMNS)
    row = {
        "distributor": "Distributor One",
        "product": "محصول یک",
        "quantity": 7.5,
    }
    if include_variables:
        columns.extend(SHIPMENTS_DETAIL_COLUMNS)
        row.update(
            {
                "explanation": "تحویل بهینه — بدون کسری نرم",
                "distributor_inventory": 4.0,
                "sales_ma_3": 20.0,
                "sales_ma_6": 18.0,
                "sales_mtd": 5.0,
                "coverage_demand": 15.0,
                "demand_coverage_required": 22.5,
                "remaining_target_units": 45.0,
                "target_units": 50.0,
                "target_coverage_required": 67.5,
                "product_inventory_plus_delivery": 11.5,
                "delivery_ma_6": 9.0,
                "has_delivery_last_6m": True,
                "smoothing_lower": 8.1,
                "smoothing_upper": 10.8,
                "inventory_plus_delivery": 11.5,
                "demand_coverage_slack": 0.0,
                "delivery_low_slack": 0.0,
                "delivery_high_slack": 0.0,
                "target_units_slack": 0.0,
                "product_total_shipped": 7.5,
                "factory_supply": 100.0,
                "factory_supply_remaining": 92.5,
            }
        )
    return RunResult(
        status="Optimal",
        objective=12.34,
        solver_name="Greedy",
        is_optimal=True,
        is_feasible=True,
        shipments=(
            Shipment("D1", "Distributor One", "P1", "محصول یک", "Product One", 7.5),
        ),
        summary=RunSummary(
            total_shipments=7.5,
            num_distributors=1,
            num_products=1,
            shipments_by_product={"Product One": 7.5},
            shipments_by_distributor={"Distributor One": 7.5},
        ),
        table=TabularData(columns=tuple(columns), rows=(row,)),
    )


class TestOptimizationXlsxExport(unittest.TestCase):
    def test_sheet_names_and_parameters(self) -> None:
        result = _fake_result()
        request = ExportRequestMeta(
            snapshot_date=date(2026, 7, 27),
            solver="Greedy",
            settings_preset="default",
            settings=OptimizationSettings(coverage_ratio=2.0),
            solver_options={"Greedy": {"unused": 1}},
        )
        workbook = build_optimization_workbook(result, request=request)
        self.assertEqual(workbook.sheetnames, ["Shipments", "Summary", "Parameters"])

        shipments = workbook["Shipments"]
        self.assertEqual(
            [cell.value for cell in shipments[2]],
            list(SHIPMENTS_BASE_COLUMNS),
        )
        self.assertEqual(shipments["C3"].value, 7.5)
        self.assertIsInstance(shipments["C3"].value, float)
        self.assertEqual(shipments["B3"].value, "محصول یک")

        parameters = workbook["Parameters"]
        values = {
            row[0].value: row[1].value
            for row in parameters.iter_rows(min_row=2, max_col=2)
        }
        self.assertEqual(parameters["A1"].value, "parameter")
        self.assertEqual(parameters["B1"].value, "value")
        self.assertEqual(values["snapshot_date"], "2026-07-27")
        self.assertEqual(values["solver"], "Greedy")
        self.assertEqual(values["settings_preset"], "default")
        self.assertEqual(values["settings.coverage_ratio"], 2.0)
        self.assertEqual(values["Greedy.unused"], 1)

    def test_detail_columns_follow_grouped_order(self) -> None:
        detail = list(SHIPMENTS_DETAIL_COLUMNS)
        self.assertEqual(detail[0], "explanation")
        sc1 = ["demand_coverage_required", "inventory_plus_delivery", "demand_coverage_slack"]
        self.assertEqual(detail[6:9], sc1)
        sc2 = [
            "target_units",
            "remaining_target_units",
            "target_coverage_required",
            "product_inventory_plus_delivery",
            "target_units_slack",
        ]
        self.assertEqual(detail[9:14], sc2)
        self.assertEqual(detail[14], "has_delivery_last_6m")
        hc1 = ["factory_supply", "product_total_shipped", "factory_supply_remaining"]
        self.assertEqual(detail[-3:], hc1)

    def test_variable_columns_when_requested(self) -> None:
        result = _fake_result(include_variables=True)
        request = ExportRequestMeta(
            snapshot_date=date(2026, 7, 27),
            solver="CBC",
            include_export_variables=True,
        )
        workbook = build_optimization_workbook(result, request=request)
        headers = [cell.value for cell in workbook["Shipments"][2]]
        self.assertEqual(
            headers,
            [shipment_column_label(column) for column in SHIPMENTS_TABLE_COLUMNS],
        )
        self.assertEqual(workbook["Shipments"]["A1"].value, "Result")
        self.assertEqual(workbook["Shipments"]["J1"].value, "Demand coverage")
        self.assertIn("required (inventory+delivery", headers[9])
        self.assertIn("inventory+delivery (country)", headers[15])
        self.assertEqual(workbook["Shipments"]["R3"].value, True)

    def test_none_becomes_blank(self) -> None:
        result = _fake_result()
        # Inject a missing optional-looking blank into a custom table row
        result = RunResult(
            status=result.status,
            objective=None,
            solver_name=result.solver_name,
            is_optimal=result.is_optimal,
            is_feasible=result.is_feasible,
            shipments=result.shipments,
            summary=result.summary,
            table=TabularData(
                columns=("distributor", "product", "quantity", "note"),
                rows=(
                    {
                        "distributor": "D",
                        "product": "P",
                        "quantity": 1,
                        "note": None,
                    },
                ),
            ),
        )
        workbook = build_optimization_workbook(
            result,
            request=ExportRequestMeta(snapshot_date=date(2026, 7, 27), solver="Greedy"),
        )
        self.assertIsNone(workbook["Shipments"]["D3"].value)
        self.assertIsNone(workbook["Summary"]["B2"].value)  # objective

    def test_write_path_and_download_filename(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "result.xlsx"
            written = write_optimization_xlsx(
                _fake_result(),
                path,
                request=ExportRequestMeta(
                    snapshot_date=date(2026, 7, 27), solver="SimulatedAnnealing"
                ),
            )
            self.assertTrue(written.exists())
            loaded = load_workbook(written)
            self.assertEqual(loaded.sheetnames[0], "Shipments")
        self.assertEqual(
            download_filename(date(2026, 7, 27), "SimulatedAnnealing"),
            "optimization_2026-07-27_SimulatedAnnealing.xlsx",
        )

    def test_shipments_sheet_formatting(self) -> None:
        result = _fake_result()
        # Two data rows so alternating fill is observable on row 3
        result = RunResult(
            status=result.status,
            objective=result.objective,
            solver_name=result.solver_name,
            is_optimal=result.is_optimal,
            is_feasible=result.is_feasible,
            shipments=result.shipments,
            summary=result.summary,
            table=TabularData(
                columns=result.table.columns,
                rows=(
                    result.table.rows[0],
                    {
                        "distributor": "Distributor Two",
                        "product": "محصول دو",
                        "quantity": 3.0,
                    },
                ),
            ),
        )
        workbook = build_optimization_workbook(
            result,
            request=ExportRequestMeta(snapshot_date=date(2026, 7, 27), solver="Greedy"),
        )
        sheet = workbook["Shipments"]
        self.assertEqual(sheet["A2"].font.color.rgb, "00FFFFFF")
        self.assertEqual(sheet["A2"].fill.fgColor.rgb, "00102A43")
        self.assertTrue(sheet["A2"].font.bold)
        self.assertEqual(sheet.freeze_panes, "A3")
        self.assertGreaterEqual(sheet.column_dimensions["A"].width, 10)
        # Second data row (row 4) should have alternate fill
        self.assertEqual(sheet["A4"].fill.fgColor.rgb, "00F0F4F8")
        self.assertFalse(sheet.sheet_view.showGridLines)


if __name__ == "__main__":
    unittest.main()
