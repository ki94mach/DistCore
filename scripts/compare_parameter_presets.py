"""
Run optimization with 2–3 parameter presets (same data, CBC) and compare results.

Use this to compare different settings (coverage ratio, weights, bounds) on the same
snapshot. All runs use the CBC solver. Results are printed and optionally saved.

Built-in presets (edit PRESETS in this file to change):
  - default:      coverage_ratio=1.5, equal weights
  - high_coverage: stiffer coverage (ratio 1.8, higher coverage weight)
  - focus_targets: emphasize target units (higher weight_target_units)

Usage:
  # Run with built-in presets (default + high_coverage + focus_targets)
  python scripts/compare_parameter_presets.py

  # Specific date and output directory
  python scripts/compare_parameter_presets.py --date 2026-02-08 --output-dir data

  # Custom presets from JSON file (see below for format)
  python scripts/compare_parameter_presets.py --presets path/to/presets.json
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import time
from datetime import date
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.optimization import ModelBuilder, OptimizationSettings, SnapshotDataLoader, solve
from src.optimization.constraints import (
    DeliveryHistoryConstraint,
    DeliverySmoothingConstraint,
    FactorySupplyConstraint,
    DistributorCoverageConstraint,
    ProductTargetUnitsConstraint,
)
from src.orchestrator.services.sql_server_db import DBConnectionFactory, SQLExecutor


CONSTRAINTS = [
    FactorySupplyConstraint(),
    DeliveryHistoryConstraint(),
    DeliverySmoothingConstraint(),
    DistributorCoverageConstraint(),
    ProductTargetUnitsConstraint(),
]

# Built-in presets: name -> OptimizationSettings (or dict for from_dict if we add it)
PRESETS: dict[str, OptimizationSettings] = {
    "default": OptimizationSettings(
        coverage_ratio=1.5,
        sales_window=6,
        delivery_lower_bound=0.9,
        delivery_upper_bound=1.2,
        weight_coverage=1.0,
        weight_target_units=1.0,
        weight_delivery=1.0,
        weight_shipment=0.0,
    ),
    "high_coverage": OptimizationSettings(
        coverage_ratio=1,
        sales_window=3,
        delivery_lower_bound=0.9,
        delivery_upper_bound=1.2,
        weight_coverage=2.0,
        weight_target_units=1.0,
        weight_delivery=1.0,
        weight_shipment=1.0,
    ),
    "focus_targets": OptimizationSettings(
        coverage_ratio=1,
        sales_window=3,
        delivery_lower_bound=0.9,
        delivery_upper_bound=1.2,
        weight_coverage=1.0,
        weight_target_units=2.0,
        weight_delivery=1.0,
        weight_shipment=1.0,
    ),
}


def _settings_from_dict(d: dict[str, Any]) -> OptimizationSettings:
    """Build OptimizationSettings from a dict (e.g. from JSON)."""
    return OptimizationSettings(
        coverage_ratio=float(d.get("coverage_ratio", 1.5)),
        sales_window=int(d.get("sales_window", 6)),
        delivery_lower_bound=float(d.get("delivery_lower_bound", 0.9)),
        delivery_upper_bound=float(d.get("delivery_upper_bound", 1.2)),
        weight_coverage=float(d.get("weight_coverage", 1.0)),
        weight_target_units=float(d.get("weight_target_units", 1.0)),
        weight_delivery=float(d.get("weight_delivery", 1.0)),
    )


def load_presets(path: Path) -> dict[str, OptimizationSettings]:
    """Load presets from JSON. Format: { "preset_name": { "coverage_ratio": 1.5, ... }, ... }."""
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)
    return {name: _settings_from_dict(v) for name, v in raw.items()}


def load_data(
    sql_executor: SQLExecutor,
    snapshot_date: date,
    database_type: str,
    settings: OptimizationSettings,
) -> Any:
    """Load optimization data from database."""
    loader = SnapshotDataLoader(sql_executor=sql_executor, database_type=database_type)
    return loader.load_optimization_data(
        snapshot_date=snapshot_date,
        snapshot_month=None,
        settings=settings,
    )


def l1_difference(result: Any, variable_values_a: dict, variable_values_b: dict) -> float:
    """Sum of |value_a - value_b| over decision variables only."""
    total = 0.0
    for (_, _), variable in result.decision_variables.items():
        va = variable_values_a.get(variable, 0.0)
        vb = variable_values_b.get(variable, 0.0)
        total += abs(va - vb)
    return total


def _distributor_label(data: Any, distributor_id: str) -> str:
    """Display name for distributor (from dimension) or ID if not available."""
    return (getattr(data, "distributor_names", None) or {}).get(distributor_id, distributor_id)


def _product_label(data: Any, product_id: str) -> str:
    """Display name for product (from dimension) or ID if not available."""
    return (getattr(data, "product_names", None) or {}).get(product_id, product_id)


def save_preset_csv(
    data: Any,
    result: Any,
    solution: Any,
    csv_path: Path,
    include_variables: bool = True,
) -> None:
    """Write one CSV (distributor, product, quantity + optional input variables) with UTF-8 BOM for Excel."""
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    if include_variables:
        fieldnames = [
            "distributor",
            "product",
            "quantity",
            "distributor_inventory",
            "sales_ma_3",
            "sales_ma_6",
            "sales_mtd",
            "coverage_demand",
            "delivery_ma_6",
            "has_delivery_last_6m",
            "target_units",
            "factory_supply",
        ]
    else:
        fieldnames = ["distributor", "product", "quantity"]
    rows: list[dict[str, Any]] = []
    for (distributor_id, product_id), variable in sorted(result.decision_variables.items()):
        quantity = round(solution.variable_values.get(variable, 0.0), 2)
        row: dict[str, Any] = {
            "distributor": _distributor_label(data, distributor_id),
            "product": _product_label(data, product_id),
            "quantity": quantity,
        }
        if include_variables:
            row["distributor_inventory"] = round(data.inventory(distributor_id, product_id), 2)
            row["sales_ma_3"] = round(data.sales_ma_3.get((distributor_id, product_id), 0.0), 2)
            row["sales_ma_6"] = round(data.sales_ma_6.get((distributor_id, product_id), 0.0), 2)
            row["sales_mtd"] = round(data.sales_mtd.get((distributor_id, product_id), 0.0), 2)
            row["coverage_demand"] = round(data.coverage_demand(distributor_id, product_id), 2)
            row["delivery_ma_6"] = round(data.delivery_moving_average(distributor_id, product_id), 2)
            row["has_delivery_last_6m"] = data.has_recent_delivery(distributor_id, product_id)
            row["target_units"] = round(data.target_units.get(product_id, 0.0), 2)
            row["factory_supply"] = round(data.factory_supply(product_id), 2)
        rows.append(row)
    with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def run_preset(
    data: Any,
    preset_name: str,
    settings: OptimizationSettings,
    solver_name: str = "CBC",
) -> dict[str, Any]:
    """Build model with given settings, solve with CBC, return metrics and solution."""
    builder = ModelBuilder(CONSTRAINTS)
    result = builder.build(data, settings_override=settings)
    start = time.perf_counter()
    solution = solve(
        result.model,
        result.decision_variables,
        method=solver_name,
        data=data,
    )
    elapsed = time.perf_counter() - start
    total_shipments = sum(
        solution.variable_values.get(v, 0.0)
        for v in result.decision_variables.values()
    )
    return {
        "preset": preset_name,
        "settings": settings,
        "result": result,
        "solution": solution,
        "objective_value": solution.objective_value,
        "total_shipments": round(total_shipments, 2),
        "status": solution.status,
        "time_seconds": round(elapsed, 3),
        "variable_values": solution.variable_values,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compare optimization results across 2–3 parameter presets (CBC).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--date",
        type=str,
        default=date.today().isoformat(),
        help="Snapshot date YYYY-MM-DD (default: today)",
    )
    parser.add_argument(
        "--database-type",
        type=str,
        default="test",
        choices=("source", "test"),
        help="Database to load from (default: test)",
    )
    parser.add_argument(
        "--config",
        type=str,
        default=None,
        help="Path to database config file",
    )
    parser.add_argument(
        "--presets",
        type=str,
        default=None,
        help="Path to JSON file with presets (else use built-in default/high_coverage/focus_targets)",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=None,
        help="Directory to save per-preset summary JSON (default: data/parameter_comparison_YYYYMMDD)",
    )
    parser.add_argument(
        "--solver",
        type=str,
        default="CBC",
        help="Solver to use (default: CBC)",
    )
    args = parser.parse_args()

    try:
        snapshot_date = date.fromisoformat(args.date)
    except ValueError:
        print(f"Invalid date: {args.date}", file=sys.stderr)
        sys.exit(1)

    if args.presets:
        presets_path = Path(args.presets)
        if not presets_path.is_file():
            print(f"Presets file not found: {presets_path}", file=sys.stderr)
            sys.exit(1)
        presets = load_presets(presets_path)
        if len(presets) < 2:
            print("Provide at least 2 presets in the JSON file.", file=sys.stderr)
            sys.exit(1)
    else:
        presets = PRESETS

    preset_names = list(presets.keys())
    print(f"Comparing {len(preset_names)} presets: {', '.join(preset_names)}")
    print(f"Snapshot date: {snapshot_date}, solver: {args.solver}")
    print("Loading data...")

    factory = (
        DBConnectionFactory.from_config_file(Path(args.config))
        if args.config
        else DBConnectionFactory()
    )
    sql_executor = SQLExecutor(factory)
    # Load once with first preset (for sales_window etc.); we override per run when building
    data = load_data(
        sql_executor,
        snapshot_date,
        args.database_type,
        presets[preset_names[0]],
    )
    print(f"Loaded: {len(data.distributors)} distributors, {len(data.products)} products")

    results: list[dict[str, Any]] = []
    for name in preset_names:
        print(f"  Running preset '{name}'...")
        row = run_preset(data, name, presets[name], solver_name=args.solver)
        results.append(row)

    # L1 vs first preset
    ref_values = results[0]["variable_values"]
    ref_result = results[0]["result"]
    for r in results:
        if r["preset"] == results[0]["preset"]:
            r["l1_vs_first"] = None
        else:
            r["l1_vs_first"] = round(
                l1_difference(ref_result, r["variable_values"], ref_values), 4
            )

    # Console table (objective = penalty from slacks; total_shipments = sum of quantity in CSV)
    print("\nParameter preset comparison:")
    print("  (Objective = minimized penalty from constraint shortfalls; Total shipments = sum of quantity column in CSV)")
    print("-" * 105)
    print(f"{'Preset':<18} {'Objective':<14} {'Total ship':<12} {'Status':<10} {'Time(s)':<8} {'L1 vs first':<12}")
    print("-" * 105)
    for r in results:
        obj = str(r["objective_value"]) if r["objective_value"] is not None else "—"
        tot = str(r.get("total_shipments", "—"))
        l1 = str(r.get("l1_vs_first")) if r.get("l1_vs_first") is not None else "—"
        print(f"{r['preset']:<18} {obj:<14} {tot:<12} {r['status']:<10} {r['time_seconds']:<8} {l1:<12}")
    print("-" * 105)

    # Summary JSON
    out_dir = args.output_dir
    if not out_dir:
        out_dir = Path(__file__).resolve().parent.parent / "data" / f"parameter_comparison_{snapshot_date:%Y%m%d}"
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    summary = {
        "snapshot_date": args.date,
        "solver": args.solver,
        "_note": "objective_value = minimized penalty (weighted slacks); total_shipments = sum of quantity in CSV",
        "presets": [
            {
                "name": r["preset"],
                "objective_value": r["objective_value"],
                "total_shipments": r.get("total_shipments"),
                "status": r["status"],
                "time_seconds": r["time_seconds"],
                "l1_vs_first": r.get("l1_vs_first"),
                "settings": {
                    "coverage_ratio": r["settings"].coverage_ratio,
                    "sales_window": r["settings"].sales_window,
                    "delivery_lower_bound": r["settings"].delivery_lower_bound,
                    "delivery_upper_bound": r["settings"].delivery_upper_bound,
                    "weight_coverage": r["settings"].weight_coverage,
                    "weight_target_units": r["settings"].weight_target_units,
                    "weight_delivery": r["settings"].weight_delivery,
                },
            }
            for r in results
        ],
    }
    summary_path = out_dir / "comparison_summary.json"
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)
    print(f"\nSummary saved to: {summary_path}")

    # Save one CSV per preset under the same output directory
    for r in results:
        safe_name = re.sub(r"[^\w\-]", "_", r["preset"]).strip("_") or "preset"
        csv_path = out_dir / f"{safe_name}.csv"
        save_preset_csv(data, r["result"], r["solution"], csv_path)
        print(f"CSV saved to: {csv_path}")


if __name__ == "__main__":
    main()
