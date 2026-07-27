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
    SHIPMENTS_VARIABLE_COLUMNS,
    build_optimization_workbook,
    download_filename,
    write_optimization_xlsx,
)
from src.optimization.service import RunResult, RunSummary, Shipment, TabularData


def _fake_result(*, include_variables: bool = False) -> RunResult:
    columns = list(SHIPMENTS_BASE_COLUMNS)
    row = {
        "distributor": "Distributor One",
        "product": "محصول یک",
        "quantity": 7.5,
    }
    if include_variables:
        columns.extend(SHIPMENTS_VARIABLE_COLUMNS)
        row.update(
            {
                "distributor_inventory": 4.0,
                "sales_ma_3": 20.0,
                "sales_ma_6": 18.0,
                "sales_mtd": 5.0,
                "coverage_demand": 15.0,
                "delivery_ma_6": 9.0,
                "has_delivery_last_6m": True,
                "target_units": 50.0,
                "factory_supply": 100.0,
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
            [cell.value for cell in shipments[1]],
            list(SHIPMENTS_BASE_COLUMNS),
        )
        self.assertEqual(shipments["C2"].value, 7.5)
        self.assertIsInstance(shipments["C2"].value, float)
        self.assertEqual(shipments["B2"].value, "محصول یک")

        parameters = workbook["Parameters"]
        values = {row[0].value: row[1].value for row in parameters.iter_rows(min_row=1, max_col=2)}
        self.assertEqual(values["snapshot_date"], "2026-07-27")
        self.assertEqual(values["solver"], "Greedy")
        self.assertEqual(values["settings_preset"], "default")
        self.assertEqual(values["settings.coverage_ratio"], 2.0)
        self.assertEqual(values["Greedy.unused"], 1)

    def test_variable_columns_when_requested(self) -> None:
        result = _fake_result(include_variables=True)
        request = ExportRequestMeta(
            snapshot_date=date(2026, 7, 27),
            solver="CBC",
            include_export_variables=True,
        )
        workbook = build_optimization_workbook(result, request=request)
        headers = [cell.value for cell in workbook["Shipments"][1]]
        self.assertEqual(
            headers,
            list(SHIPMENTS_BASE_COLUMNS) + list(SHIPMENTS_VARIABLE_COLUMNS),
        )
        self.assertEqual(workbook["Shipments"]["J2"].value, True)

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
        self.assertIsNone(workbook["Shipments"]["D2"].value)
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


if __name__ == "__main__":
    unittest.main()
