"""Excel (.xlsx) export for optimization run results."""

from __future__ import annotations

from dataclasses import dataclass, fields
from datetime import date
from pathlib import Path
from typing import Any, Mapping, Optional, Union

from openpyxl import Workbook
from openpyxl.worksheet.worksheet import Worksheet

from src.optimization.data import OptimizationSettings
from src.optimization.service import RunResult

SHIPMENTS_BASE_COLUMNS = ("distributor", "product", "quantity")
SHIPMENTS_VARIABLE_COLUMNS = (
    "distributor_inventory",
    "sales_ma_3",
    "sales_ma_6",
    "sales_mtd",
    "coverage_demand",
    "delivery_ma_6",
    "has_delivery_last_6m",
    "target_units",
    "factory_supply",
)


@dataclass(frozen=True)
class ExportRequestMeta:
    """Request echo written to the Parameters sheet."""

    snapshot_date: date
    solver: str
    settings: Optional[OptimizationSettings] = None
    settings_preset: Optional[str] = None
    solver_options: Optional[Mapping[str, Mapping[str, Any]]] = None
    include_export_variables: bool = False


def _excel_value(value: Any) -> Any:
    """Convert Python values to Excel-safe cell contents (None -> blank)."""
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def _append_kv(sheet: Worksheet, key: str, value: Any) -> None:
    sheet.append([key, _excel_value(value)])


def _write_shipments(sheet: Worksheet, result: RunResult) -> None:
    columns = list(result.table.columns)
    sheet.append(columns)
    for row in result.table.rows:
        sheet.append([_excel_value(row.get(column)) for column in columns])


def _write_summary(sheet: Worksheet, result: RunResult) -> None:
    _append_kv(sheet, "status", result.status)
    _append_kv(sheet, "objective", result.objective)
    _append_kv(sheet, "solver_name", result.solver_name)
    _append_kv(sheet, "is_optimal", result.is_optimal)
    _append_kv(sheet, "is_feasible", result.is_feasible)
    _append_kv(sheet, "total_shipments", result.summary.total_shipments)
    _append_kv(sheet, "num_distributors", result.summary.num_distributors)
    _append_kv(sheet, "num_products", result.summary.num_products)

    sheet.append([])
    sheet.append(["shipments_by_product", "quantity"])
    for product, quantity in result.summary.shipments_by_product.items():
        sheet.append([_excel_value(product), _excel_value(quantity)])

    sheet.append([])
    sheet.append(["shipments_by_distributor", "quantity"])
    for distributor, quantity in result.summary.shipments_by_distributor.items():
        sheet.append([_excel_value(distributor), _excel_value(quantity)])


def _resolved_settings(request: ExportRequestMeta) -> OptimizationSettings:
    return request.settings if request.settings is not None else OptimizationSettings()


def _write_parameters(sheet: Worksheet, request: ExportRequestMeta) -> None:
    _append_kv(sheet, "snapshot_date", request.snapshot_date)
    _append_kv(sheet, "solver", request.solver)
    _append_kv(sheet, "settings_preset", request.settings_preset or "")
    _append_kv(sheet, "include_export_variables", request.include_export_variables)

    settings = _resolved_settings(request)
    for field in fields(OptimizationSettings):
        _append_kv(sheet, f"settings.{field.name}", getattr(settings, field.name))

    options = request.solver_options or {}
    for solver_name, option_map in options.items():
        for option_name, option_value in option_map.items():
            _append_kv(sheet, f"{solver_name}.{option_name}", option_value)


def build_optimization_workbook(
    result: RunResult,
    *,
    request: ExportRequestMeta,
) -> Workbook:
    """Build a workbook with Shipments, Summary, and Parameters sheets."""
    workbook = Workbook()
    shipments = workbook.active
    shipments.title = "Shipments"
    _write_shipments(shipments, result)

    summary = workbook.create_sheet("Summary")
    _write_summary(summary, result)

    parameters = workbook.create_sheet("Parameters")
    _write_parameters(parameters, request)
    return workbook


def write_optimization_xlsx(
    result: RunResult,
    path: Union[str, Path],
    *,
    request: ExportRequestMeta,
) -> Path:
    """Write the optimization workbook to ``path`` and return that path."""
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    workbook = build_optimization_workbook(result, request=request)
    workbook.save(output)
    return output


def download_filename(snapshot_date: date, solver: str) -> str:
    """Human-friendly attachment filename for HTTP downloads."""
    safe_solver = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in solver)
    return f"optimization_{snapshot_date.isoformat()}_{safe_solver}.xlsx"


__all__ = [
    "ExportRequestMeta",
    "SHIPMENTS_BASE_COLUMNS",
    "SHIPMENTS_VARIABLE_COLUMNS",
    "build_optimization_workbook",
    "download_filename",
    "write_optimization_xlsx",
]
