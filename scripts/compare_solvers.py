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
   - **Solution difference (L1 vs reference)**: For each solver, sum of
     |x_solver - x_reference| over decision variables. Shows how much the
     allocation differs from the reference (e.g. CBC). Useful to see if
     heuristics are close to the optimal solution.

3. **Reference solver**: Use an exact LP solver (CBC, GLPK, or Scipy) as
   reference. Compare others against it (objective gap, L1 difference).

4. **How to interpret**:
   - Same objective + feasible → solvers agree (or one is optimal, one feasible).
   - Higher objective (heuristic) → acceptable if within a few % and time is critical.
   - Large L1 difference with similar objective → multiple near-optimal solutions.
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
from src.optimization.solver import get_available_solver_names
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


def l1_difference(
    result: Any,
    variable_values_a: dict,
    variable_values_b: dict,
) -> float:
    """Sum of |value_a - value_b| over decision variables only."""
    total = 0.0
    for (_, _), variable in result.decision_variables.items():
        va = variable_values_a.get(variable, 0.0)
        vb = variable_values_b.get(variable, 0.0)
        total += abs(va - vb)
    return total


def run_comparison(
    snapshot_date: date,
    database_type: str = "test",
    config_path: str | None = None,
    settings: OptimizationSettings | None = None,
) -> list[dict[str, Any]]:
    """Load data once, build model once, run each available solver and collect metrics."""
    if settings is None:
        settings = OptimizationSettings()

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

    # Run reference solver first (exact LP) so we can compute L1 vs others
    exact = [s for s in available if s in ("CBC", "GLPK", "Scipy")]
    reference_solver = exact[0] if exact else available[0]
    order = [reference_solver] + [s for s in available if s != reference_solver]
    reference_values: dict | None = None

    rows: list[dict[str, Any]] = []
    for solver_name in order:
        start = time.perf_counter()
        try:
            solution = solve(
                result.model,
                result.decision_variables,
                method=solver_name,
                data=data,
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
                "l1_vs_reference": None,
                "total_delivery": None,
                "error": str(e),
            })
            continue
        elapsed = time.perf_counter() - start

        l1_ref = None
        if reference_values is not None:
            l1_ref = l1_difference(
                result,
                solution.variable_values,
                reference_values,
            )
        if solver_name == reference_solver:
            reference_values = solution.variable_values

        # Calculate total delivery (sum of all decision variable values)
        total_delivery = sum(
            solution.variable_values.get(v, 0.0)
            for v in result.decision_variables.values()
        )

        rows.append({
            "solver": solver_name,
            "status": solution.status,
            "is_optimal": solution.is_optimal,
            "is_feasible": solution.is_feasible,
            "objective_value": round(solution.objective_value, 4) if solution.objective_value is not None else None,
            "time_seconds": round(elapsed, 3),
            "l1_vs_reference": round(l1_ref, 4) if l1_ref is not None else None,
            "total_delivery": round(total_delivery, 2),
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
        "--output",
        type=str,
        default=None,
        help="Output JSON path (default: data/solver_comparison_YYYYMMDD.json)",
    )
    parser.add_argument(
        "--coverage-ratio",
        type=float,
        default=None,
        help="Coverage ratio multiplier (default: from OptimizationSettings)",
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
        "--weight-coverage",
        type=float,
        default=None,
        help="Weight for coverage slack in objective (default: from OptimizationSettings)",
    )
    parser.add_argument(
        "--weight-target-units",
        type=float,
        default=None,
        help="Weight for target units slack in objective (default: from OptimizationSettings)",
    )
    parser.add_argument(
        "--weight-delivery",
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
    args = parser.parse_args()

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
        args.sales_window is not None,
        args.delivery_lower_bound is not None,
        args.delivery_upper_bound is not None,
        args.weight_coverage is not None,
        args.weight_target_units is not None,
        args.weight_delivery is not None,
        args.weight_shipment is not None,
    ]):
        # Start with defaults and override only provided values
        default_settings = OptimizationSettings()
        settings = OptimizationSettings(
            coverage_ratio=args.coverage_ratio if args.coverage_ratio is not None else default_settings.coverage_ratio,
            sales_window=args.sales_window if args.sales_window is not None else default_settings.sales_window,
            delivery_lower_bound=args.delivery_lower_bound if args.delivery_lower_bound is not None else default_settings.delivery_lower_bound,
            delivery_upper_bound=args.delivery_upper_bound if args.delivery_upper_bound is not None else default_settings.delivery_upper_bound,
            weight_coverage=args.weight_coverage if args.weight_coverage is not None else default_settings.weight_coverage,
            weight_target_units=args.weight_target_units if args.weight_target_units is not None else default_settings.weight_target_units,
            weight_delivery=args.weight_delivery if args.weight_delivery is not None else default_settings.weight_delivery,
            weight_shipment=args.weight_shipment if args.weight_shipment is not None else default_settings.weight_shipment,
        )
        print(f"Using custom settings: coverage_ratio={settings.coverage_ratio}, "
              f"sales_window={settings.sales_window}, "
              f"weights=(coverage={settings.weight_coverage}, "
              f"target_units={settings.weight_target_units}, "
              f"delivery={settings.weight_delivery}, "
              f"shipment={settings.weight_shipment})")

    print(f"Comparing solvers for snapshot date {snapshot_date} ({args.database_type} DB)")
    print("Loading data and building model...")
    try:
        rows = run_comparison(
            snapshot_date=snapshot_date,
            database_type=args.database_type,
            config_path=args.config,
            settings=settings,
        )
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    # Console table
    print("\nSolver comparison:")
    print("-" * 110)
    print(f"{'Solver':<20} {'Status':<12} {'Optimal':<8} {'Objective':<12} {'Time(s)':<10} {'L1 vs ref':<12} {'Total delivery':<15}")
    print("-" * 110)
    for r in rows:
        obj = str(r["objective_value"]) if r["objective_value"] is not None else "—"
        l1 = str(r["l1_vs_reference"]) if r.get("l1_vs_reference") is not None else "—"
        tot_del = str(r["total_delivery"]) if r.get("total_delivery") is not None else "—"
        err = f" ({r['error'][:30]}...)" if r.get("error") else ""
        print(f"{r['solver']:<20} {r['status']:<12} {str(r['is_optimal']):<8} {obj:<12} {r['time_seconds']:<10} {l1:<12} {tot_del:<15}{err}")
    print("-" * 110)

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
