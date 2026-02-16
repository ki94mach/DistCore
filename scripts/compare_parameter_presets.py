"""
Run optimization with 2–3 parameter presets and compare results.

Use this to compare different settings (coverage ratio, weights, bounds) on the same
snapshot with a selected solver. Results are printed and optionally saved.

Built-in presets (edit PRESETS in this file to change):
  - default:      coverage_ratio=1.5, target_coverage_ratio=1.5, equal weights
  - high_coverage: stiffer coverage (ratio 1, higher coverage weight)
  - focus_targets: emphasize target units (higher weight_target_units)

Usage:
  # Interactive: select solver, then use built-in presets
  python scripts/compare_parameter_presets.py

  # Non-interactive: specify solver and date
  python scripts/compare_parameter_presets.py --solver CBC --date 2026-02-08

  # Custom presets from JSON file
  python scripts/compare_parameter_presets.py --solver SimulatedAnnealing --presets path/to/presets.json
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
    DemandCoverageConstraint,
    ProductTargetUnitsConstraint,
    ShipmentMinimizationConstraint,
)
from src.optimization.solvers import (
    SOLVER_PRIORITY,
    get_available_solver_names,
    is_solver_available,
)
from src.orchestrator.services.sql_server_db import DBConnectionFactory, SQLExecutor


CONSTRAINTS = [
    FactorySupplyConstraint(),
    DeliveryHistoryConstraint(),
    DeliverySmoothingConstraint(),
    DemandCoverageConstraint(),
    ProductTargetUnitsConstraint(),
    ShipmentMinimizationConstraint(),
]

# Built-in presets: name -> OptimizationSettings (or dict for from_dict if we add it)
PRESETS: dict[str, OptimizationSettings] = {
    "default": OptimizationSettings(
        coverage_ratio=1.5,
        target_coverage_ratio=1.5,
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
        target_coverage_ratio=1,
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
        target_coverage_ratio=1,
        sales_window=3,
        delivery_lower_bound=0.9,
        delivery_upper_bound=1.2,
        weight_coverage=1.0,
        weight_target_units=2.0,
        weight_delivery=1.0,
        weight_shipment=1.0,
    ),
}

# Solver-specific preset options (e.g., for SimulatedAnnealing)
SOLVER_PRESETS: dict[str, dict[str, dict[str, Any]]] = {
    "SimulatedAnnealing": {
        "default": {
            "max_iter": 5000,
            "initial_temp": 1000.0,
            "min_temp": 0.01,
            "cooling_rate": 0.995,
            "step_scale": 0.2,
            "transfer_fraction": 0.5,
            "initial_scale": 0.15,
            "decrease_bias": 0.6,
        },
        "fast": {
            "max_iter": 2000,
            "initial_temp": 500.0,
            "min_temp": 0.1,
            "cooling_rate": 0.99,
            "step_scale": 0.15,
            "transfer_fraction": 0.5,
            "initial_scale": 0.15,
            "decrease_bias": 0.6,
        },
        "thorough": {
            "max_iter": 10000,
            "initial_temp": 2000.0,
            "min_temp": 0.001,
            "cooling_rate": 0.999,
            "step_scale": 0.2,
            "transfer_fraction": 0.5,
            "initial_scale": 0.15,
            "decrease_bias": 0.6,
        },
    },
}


def _settings_from_dict(d: dict[str, Any]) -> OptimizationSettings:
    """Build OptimizationSettings from a dict (e.g. from JSON)."""
    return OptimizationSettings(
        coverage_ratio=float(d.get("coverage_ratio", 1.5)),
        target_coverage_ratio=float(d.get("target_coverage_ratio", 1.5)),
        sales_window=int(d.get("sales_window", 6)),
        delivery_lower_bound=float(d.get("delivery_lower_bound", 0.9)),
        delivery_upper_bound=float(d.get("delivery_upper_bound", 1.2)),
        weight_coverage=float(d.get("weight_coverage", 1.0)),
        weight_target_units=float(d.get("weight_target_units", 1.0)),
        weight_delivery=float(d.get("weight_delivery", 1.0)),
    )


def load_presets(path: Path) -> dict[str, OptimizationSettings]:
    """Load presets from JSON. Format: { "preset_name": { "coverage_ratio": 1.5, "target_coverage_ratio": 1.5, ... }, ... }."""
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
    solver_options: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build model with given settings, solve with specified solver, return metrics and solution."""
    builder = ModelBuilder(CONSTRAINTS)
    result = builder.build(data, settings_override=settings)
    start = time.perf_counter()
    solution = solve(
        result.model,
        result.decision_variables,
        method=solver_name,
        data=data,
        solver_options=solver_options,
    )
    elapsed = time.perf_counter() - start
    
    # Calculate total delivery (sum of all decision variable values)
    total_delivery = sum(
        solution.variable_values.get(v, 0.0)
        for v in result.decision_variables.values()
    )
    
    # Calculate sum of slack variables by type
    slack_coverage = 0.0
    slack_units = 0.0
    slack_delivery_low = 0.0
    slack_delivery_high = 0.0
    
    for slack_var in result.slack_variables:
        value = solution.variable_values.get(slack_var, 0.0)
        if slack_var.name.startswith("s_demand_coverage_"):
            slack_coverage += value
        elif slack_var.name.startswith("s_units_"):
            slack_units += value
        elif slack_var.name.startswith("s_delivery_low_"):
            slack_delivery_low += value
        elif slack_var.name.startswith("s_delivery_high_"):
            slack_delivery_high += value
    
    return {
        "preset": preset_name,
        "settings": settings,
        "result": result,
        "solution": solution,
        "objective_value": solution.objective_value,
        "total_delivery": int(round(total_delivery)),
        "status": solution.status,
        "is_optimal": solution.is_optimal,
        "is_feasible": solution.is_feasible,
        "time_seconds": round(elapsed, 3),
        "slack_coverage": int(round(slack_coverage)),
        "slack_units": int(round(slack_units)),
        "slack_delivery_low": int(round(slack_delivery_low)),
        "slack_delivery_high": int(round(slack_delivery_high)),
        "variable_values": solution.variable_values,
    }


def select_solver_interactive() -> str:
    """Interactively select a solver from available options."""
    available = get_available_solver_names()
    
    labels = {
        "CBC": "CBC (Coin-or Branch and Cut) - Recommended",
        "GLPK": "GLPK (GNU Linear Programming Kit)",
        "Scipy": "Scipy (HiGHS) - exact LP, no PuLP",
        "Greedy": "Greedy - heuristic baseline, fast",
        "SimulatedAnnealing": "Simulated Annealing - metaheuristic",
    }
    
    print("\nSelect Solver (priority order for evaluation):")
    solver_map = {}
    for i, name in enumerate(SOLVER_PRIORITY, start=1):
        desc = labels.get(name, name)
        if name in available:
            print(f"  {i}. {desc}")
        else:
            print(f"  {i}. {desc} [not available]")
        solver_map[str(i)] = name
    
    default = "1"
    prompt = f"Select solver (1-{len(SOLVER_PRIORITY)}, default={default}): "
    solver_choice = input(prompt).strip() or default
    selected = solver_map.get(solver_choice, SOLVER_PRIORITY[0])
    
    if selected not in available:
        print(f"Warning: {selected} is not available. Using {available[0]} instead.", file=sys.stderr)
        selected = available[0]
    
    return selected


def select_solver_preset_interactive(solver_name: str) -> dict[str, Any] | None:
    """Interactively select solver-specific preset options if available."""
    if solver_name not in SOLVER_PRESETS:
        return None
    
    presets = SOLVER_PRESETS[solver_name]
    print(f"\nSelect {solver_name} preset (or press Enter to skip):")
    preset_map = {}
    for i, (name, opts) in enumerate(presets.items(), start=1):
        print(f"  {i}. {name}")
        preset_map[str(i)] = name
    
    prompt = f"Select preset (1-{len(presets)}, or Enter to skip): "
    preset_choice = input(prompt).strip()
    
    if not preset_choice:
        return None
    
    selected_preset = preset_map.get(preset_choice)
    if selected_preset:
        return {solver_name: presets[selected_preset]}
    return None


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compare optimization results across 2–3 parameter presets.",
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
        default=None,
        help="Solver to use (if not provided, will prompt interactively)",
    )
    parser.add_argument(
        "--solver-preset",
        type=str,
        default=None,
        help="Solver-specific preset name (e.g., 'fast', 'thorough' for SimulatedAnnealing)",
    )
    parser.add_argument(
        "--non-interactive",
        action="store_true",
        help="Skip interactive prompts (requires --solver)",
    )
    args = parser.parse_args()

    try:
        snapshot_date = date.fromisoformat(args.date)
    except ValueError:
        print(f"Invalid date: {args.date}", file=sys.stderr)
        sys.exit(1)

    # Select solver
    if args.solver:
        solver_name = args.solver
        if not is_solver_available(solver_name):
            print(f"Warning: Solver '{solver_name}' is not available.", file=sys.stderr)
            available = get_available_solver_names()
            if available:
                print(f"Available solvers: {', '.join(available)}", file=sys.stderr)
                if not args.non_interactive:
                    solver_name = select_solver_interactive()
                else:
                    print(f"Using first available solver: {available[0]}", file=sys.stderr)
                    solver_name = available[0]
            else:
                print("No solvers available!", file=sys.stderr)
                sys.exit(1)
    elif args.non_interactive:
        print("Error: --non-interactive requires --solver", file=sys.stderr)
        sys.exit(1)
    else:
        solver_name = select_solver_interactive()

    # Select solver-specific preset if applicable
    solver_options = None
    if solver_name in SOLVER_PRESETS:
        if args.solver_preset:
            if args.solver_preset in SOLVER_PRESETS[solver_name]:
                solver_options = {solver_name: SOLVER_PRESETS[solver_name][args.solver_preset]}
            else:
                print(f"Warning: Solver preset '{args.solver_preset}' not found for {solver_name}.", file=sys.stderr)
                print(f"Available presets: {', '.join(SOLVER_PRESETS[solver_name].keys())}", file=sys.stderr)
        elif not args.non_interactive:
            solver_options = select_solver_preset_interactive(solver_name)

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
    print(f"\nComparing {len(preset_names)} presets: {', '.join(preset_names)}")
    print(f"Snapshot date: {snapshot_date}, solver: {solver_name}")
    if solver_options:
        print(f"Solver options: {solver_options}")
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
        row = run_preset(data, name, presets[name], solver_name=solver_name, solver_options=solver_options)
        results.append(row)

    # Console table (matching compare_solvers.py format)
    print("\nParameter preset comparison:")
    print("-" * 188)
    print(f"{'Preset':<20} {'Status':<12} {'Optimal':<8} {'Objective':<12} {'Time(s)':<10} {'Total delivery':<15} {'Slack: Coverage':<18} {'Slack: Units':<15} {'Slack: Del Low':<18} {'Slack: Del High':<18}")
    print("-" * 188)
    for r in results:
        obj = str(int(round(r["objective_value"]))) if r["objective_value"] is not None else "—"
        tot_del = str(r.get("total_delivery", "—"))
        slack_cov = str(r.get("slack_coverage", "—"))
        slack_units = str(r.get("slack_units", "—"))
        slack_del_low = str(r.get("slack_delivery_low", "—"))
        slack_del_high = str(r.get("slack_delivery_high", "—"))
        print(f"{r['preset']:<20} {r['status']:<12} {str(r.get('is_optimal', False)):<8} {obj:<12} {r['time_seconds']:<10} {tot_del:<15} {slack_cov:<18} {slack_units:<15} {slack_del_low:<18} {slack_del_high:<18}")
    print("-" * 188)

    # Summary JSON
    out_dir = args.output_dir
    if not out_dir:
        out_dir = Path(__file__).resolve().parent.parent / "data" / f"parameter_comparison_{snapshot_date:%Y%m%d}"
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    summary = {
        "snapshot_date": args.date,
        "solver": solver_name,
        "solver_options": solver_options,
        "presets": [
            {
                "name": r["preset"],
                "status": r["status"],
                "is_optimal": r.get("is_optimal", False),
                "is_feasible": r.get("is_feasible", False),
                "objective_value": int(round(r["objective_value"])) if r["objective_value"] is not None else None,
                "time_seconds": r["time_seconds"],
                "total_delivery": r.get("total_delivery"),
                "slack_coverage": r.get("slack_coverage"),
                "slack_units": r.get("slack_units"),
                "slack_delivery_low": r.get("slack_delivery_low"),
                "slack_delivery_high": r.get("slack_delivery_high"),
                "settings": {
                    "coverage_ratio": int(round(r["settings"].coverage_ratio)),
                    "target_coverage_ratio": int(round(r["settings"].target_coverage_ratio)),
                    "sales_window": r["settings"].sales_window,
                    "delivery_lower_bound": r["settings"].delivery_lower_bound,
                    "delivery_upper_bound": r["settings"].delivery_upper_bound,
                    "weight_coverage": int(round(r["settings"].weight_coverage)),
                    "weight_target_units": int(round(r["settings"].weight_target_units)),
                    "weight_delivery": int(round(r["settings"].weight_delivery)),
                    "weight_shipment": int(round(r["settings"].weight_shipment)),
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
