"""
Compare optimization solvers on the same input (same data, same model).

Methodology
----------
1. **Controlled input**: Use one snapshot date, one database, one set of
   optimization settings. Load data once and build the model once.

2. **Metrics to compare**:
   - **Objective value** (min): Lower is better. Exact LP solvers (CBC, GLPK, Scipy)
     should give the same (optimal) value; heuristics (Greedy, SA) may be higher.
   - **Status / Optimal**: Prefer "Optimal" over "Feasible" for production.
   - **Solve time (seconds)**: Wall-clock time per solver. Heuristics are often
     faster than LP for large instances; LP gives proven optimum.
   - **Slack variables**: Sum of slack variables by type (coverage, units, delivery low/high)
     to track violations from soft constraints.

3. **How to interpret**:
   - Same objective + feasible → solvers agree (or one is optimal, one feasible).
   - Higher objective (heuristic) → acceptable if within a few % and time is critical.
   - Slack variables → higher values indicate more violations of soft constraints.
   - Use the report to choose: exact solver for quality, heuristic for speed/fallback.

Usage
-----
  # Compare all available solvers (uses today's date, test DB, default settings)
  python scripts/compare_solvers.py

  # Specific date and output file
  python scripts/compare_solvers.py --date 2026-02-08 --output data/solver_comparison.json

  # With database config and database type
  python scripts/compare_solvers.py --date 2026-02-07 --config path/to/db_config.json --database-type source
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import date
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.optimization import ModelBuilder, OptimizationSettings, solve, SnapshotDataLoader
from src.optimization.solvers import (
    get_available_solver_names,
    get_default_settings,
    get_available_presets,
    get_preset_options,
    get_default_options,
)
from src.optimization.constraints import (
    DeliveryHistoryConstraint,
    DeliverySmoothingConstraint,
    FactorySupplyConstraint,
    DemandCoverageConstraint,
    ProductTargetUnitsConstraint,
    ShipmentMinimizationConstraint,
)
from src.orchestrator.services.sql_server_db import DBConnectionFactory, SQLExecutor
from src.orchestrator.services.vpn import ensure_vpn_connected


CONSTRAINTS = [
    FactorySupplyConstraint(),
    DeliveryHistoryConstraint(),
    DeliverySmoothingConstraint(),
    DemandCoverageConstraint(),
    ProductTargetUnitsConstraint(),
    ShipmentMinimizationConstraint(),
]


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


def build_model(data: Any, settings: OptimizationSettings | None = None) -> Any:
    """Build model and return (model, decision_variables) result."""
    builder = ModelBuilder(CONSTRAINTS)
    return builder.build(data, settings_override=settings)


def run_comparison(
    snapshot_date: date,
    database_type: str = "prod",
    config_path: str | None = None,
    settings: OptimizationSettings | None = None,
    solver_options: dict[str, dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Load data once, build model once, run each available solver and collect metrics.
    
    Args:
        snapshot_date: Date to use for snapshot
        database_type: Database type ("prod" or "source")
        config_path: Optional path to database config file
        settings: Optional OptimizationSettings (uses default if None)
        solver_options: Optional solver-specific options dict (e.g., {"SimulatedAnnealing": {"max_iter": 10000}})
    """
    if settings is None:
        settings = get_default_settings()

    factory = (
        DBConnectionFactory.from_config_file(Path(config_path))
        if config_path
        else DBConnectionFactory()
    )
    sql_executor = SQLExecutor(factory)

    data = load_data(sql_executor, snapshot_date, database_type, settings)
    result = build_model(data, settings=settings)

    available = get_available_solver_names()
    if not available:
        raise RuntimeError("No solvers available. Install pulp and/or scipy.")

    rows: list[dict[str, Any]] = []
    for solver_name in available:
        start = time.perf_counter()
        try:
            # Get solver-specific options if provided
            solver_opts = (solver_options or {}).get(solver_name) or {}
            solution = solve(
                result.model,
                result.decision_variables,
                method=solver_name,
                data=data,
                solver_options={solver_name: solver_opts} if solver_opts else None,
            )
        except Exception as e:
            elapsed = time.perf_counter() - start
            rows.append({
                "solver": solver_name,
                "status": "Error",
                "is_optimal": False,
                "is_feasible": False,
                "objective_value": None,
                "time_seconds": round(elapsed, 3),
                "total_delivery": None,
                "slack_coverage": None,
                "slack_units": None,
                "slack_delivery_low": None,
                "slack_delivery_high": None,
                "error": str(e),
            })
            continue
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

        rows.append({
            "solver": solver_name,
            "status": solution.status,
            "is_optimal": solution.is_optimal,
            "is_feasible": solution.is_feasible,
            "objective_value": round(solution.objective_value, 4) if solution.objective_value is not None else None,
            "time_seconds": round(elapsed, 3),
            "total_delivery": round(total_delivery, 2),
            "slack_coverage": round(slack_coverage, 4),
            "slack_units": round(slack_units, 4),
            "slack_delivery_low": round(slack_delivery_low, 4),
            "slack_delivery_high": round(slack_delivery_high, 4),
            "error": None,
        })

    return rows


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compare optimization solvers on the same input.",
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
        default="prod",
        choices=("source", "prod"),
        help="Database to load from (default: test)",
    )
    parser.add_argument(
        "--config",
        type=str,
        default=None,
        help="Path to database config file",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Output JSON path (default: data/solver_comparison_YYYYMMDD.json)",
    )
    parser.add_argument(
        "--coverage-ratio",
        type=float,
        default=None,
        help="Distributor coverage ratio multiplier (SC1) (default: from OptimizationSettings)",
    )
    parser.add_argument(
        "--target-coverage-ratio",
        type=float,
        default=None,
        help="Target units coverage ratio multiplier (SC2) (default: from OptimizationSettings)",
    )
    parser.add_argument(
        "--sales-window",
        type=int,
        default=None,
        choices=(3, 6),
        help="Sales moving average window in months: 3 or 6 (default: from OptimizationSettings)",
    )
    parser.add_argument(
        "--delivery-lower-bound",
        type=float,
        default=None,
        help="Delivery lower bound (default: from OptimizationSettings)",
    )
    parser.add_argument(
        "--delivery-upper-bound",
        type=float,
        default=None,
        help="Delivery upper bound (default: from OptimizationSettings)",
    )
    parser.add_argument(
        "--weight-demand",
        type=float,
        default=None,
        help="Weight for demand coverage slack in objective (default: from OptimizationSettings)",
    )
    parser.add_argument(
        "--weight-target-units",
        type=float,
        default=None,
        help="Weight for target units slack in objective (default: from OptimizationSettings)",
    )
    parser.add_argument(
        "--weight-smoothing",
        type=float,
        default=None,
        help="Weight for delivery smoothing slack in objective (default: from OptimizationSettings)",
    )
    parser.add_argument(
        "--weight-shipment",
        type=float,
        default=None,
        help="Weight for shipment slack in objective (default: from OptimizationSettings)",
    )
    parser.add_argument(
        "--solver-preset",
        type=str,
        default=None,
        help="Solver preset name to use for all solvers (e.g., 'fast', 'thorough' for SimulatedAnnealing)",
    )
    args = parser.parse_args()

    # SQL Server is behind the corporate VPN — make sure it is up.
    ensure_vpn_connected()

    try:
        snapshot_date = date.fromisoformat(args.date)
    except ValueError:
        print(f"Invalid date: {args.date}", file=sys.stderr)
        sys.exit(1)

    out_path = args.output
    if not out_path:
        out_path = Path(__file__).resolve().parent.parent / "data" / f"solver_comparison_{snapshot_date:%Y%m%d}.json"
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # Build custom settings if any parameters provided
    settings = None
    if any([
        args.coverage_ratio is not None,
        args.target_coverage_ratio is not None,
        args.sales_window is not None,
        args.delivery_lower_bound is not None,
        args.delivery_upper_bound is not None,
        args.weight_demand is not None,
        args.weight_target_units is not None,
        args.weight_smoothing is not None,
        args.weight_shipment is not None,
    ]):
        # Start with defaults and override only provided values
        default_settings = get_default_settings()
        settings = OptimizationSettings(
            coverage_ratio=args.coverage_ratio if args.coverage_ratio is not None else default_settings.coverage_ratio,
            target_coverage_ratio=args.target_coverage_ratio if args.target_coverage_ratio is not None else default_settings.target_coverage_ratio,
            sales_window=args.sales_window if args.sales_window is not None else default_settings.sales_window,
            delivery_lower_bound=args.delivery_lower_bound if args.delivery_lower_bound is not None else default_settings.delivery_lower_bound,
            delivery_upper_bound=args.delivery_upper_bound if args.delivery_upper_bound is not None else default_settings.delivery_upper_bound,
            weight_demand=args.weight_demand if args.weight_demand is not None else default_settings.weight_demand,
            weight_target_units=args.weight_target_units if args.weight_target_units is not None else default_settings.weight_target_units,
            weight_smoothing=args.weight_smoothing if args.weight_smoothing is not None else default_settings.weight_smoothing,
            weight_shipment=args.weight_shipment if args.weight_shipment is not None else default_settings.weight_shipment,
        )
        print(f"Using custom settings: coverage_ratio={settings.coverage_ratio}, target_coverage_ratio={settings.target_coverage_ratio}, "
              f"sales_window={settings.sales_window}, "
              f"weights=(demand={settings.weight_demand}, "
              f"target_units={settings.weight_target_units}, "
              f"smoothing={settings.weight_smoothing}, "
              f"shipment={settings.weight_shipment})")
    
    # Build solver options if preset specified
    solver_options = None
    if args.solver_preset:
        # Apply the preset to all solvers that support it
        solver_options = {}
        available = get_available_solver_names()
        for solver_name in available:
            available_presets = get_available_presets(solver_name)
            if args.solver_preset in available_presets:
                preset_opts = get_preset_options(solver_name, args.solver_preset)
                if preset_opts:
                    solver_options[solver_name] = preset_opts
                    print(f"Using '{args.solver_preset}' preset for {solver_name}")
            else:
                # Use defaults for solvers without this preset
                default_opts = get_default_options(solver_name)
                if default_opts:
                    solver_options[solver_name] = default_opts

    print(f"Comparing solvers for snapshot date {snapshot_date} ({args.database_type} DB)")
    print("Loading data and building model...")
    try:
        rows = run_comparison(
            snapshot_date=snapshot_date,
            database_type=args.database_type,
            config_path=args.config,
            settings=settings,
            solver_options=solver_options,
        )
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    # Console table
    print("\nSolver comparison:")
    print("-" * 188)
    print(f"{'Solver':<20} {'Status':<12} {'Optimal':<8} {'Objective':<12} {'Time(s)':<10} {'Total delivery':<15} {'Slack: Coverage':<18} {'Slack: Units':<15} {'Slack: Del Low':<18} {'Slack: Del High':<18}")
    print("-" * 188)
    for r in rows:
        obj = str(r["objective_value"]) if r["objective_value"] is not None else "—"
        tot_del = str(r["total_delivery"]) if r.get("total_delivery") is not None else "—"
        slack_cov = str(r["slack_coverage"]) if r.get("slack_coverage") is not None else "—"
        slack_units = str(r["slack_units"]) if r.get("slack_units") is not None else "—"
        slack_del_low = str(r["slack_delivery_low"]) if r.get("slack_delivery_low") is not None else "—"
        slack_del_high = str(r["slack_delivery_high"]) if r.get("slack_delivery_high") is not None else "—"
        err = f" ({r['error'][:30]}...)" if r.get("error") else ""
        print(f"{r['solver']:<20} {r['status']:<12} {str(r['is_optimal']):<8} {obj:<12} {r['time_seconds']:<10} {tot_del:<15} {slack_cov:<18} {slack_units:<15} {slack_del_low:<18} {slack_del_high:<18}{err}")
    print("-" * 188)

    report = {
        "snapshot_date": args.date,
        "database_type": args.database_type,
        "solvers": rows,
    }
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    print(f"\nReport saved to: {out_path}")


if __name__ == "__main__":
    main()
