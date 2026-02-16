"""Interactive CLI for running optimization with database data.

This script provides an interactive menu-driven interface to:
1. Configure optimization parameters
2. Load optimization data from database snapshot tables
3. Build the optimization model
4. Solve the optimization problem
5. Display and save results

Usage:
    python scripts/run_optimization_production.py
"""

from __future__ import annotations

import csv
import json
import sys
from datetime import date
from pathlib import Path
from typing import Any, Optional

# Add project root to Python path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.optimization import (
    OptimizationSettings,
    ModelBuilder,
    solve,
    SnapshotDataLoader,
)
from src.optimization.solvers import SOLVER_PRIORITY, get_available_solver_names
from src.optimization.constraints import (
    DeliveryHistoryConstraint,
    DeliverySmoothingConstraint,
    FactorySupplyConstraint,
    DemandCoverageConstraint,
    ProductTargetUnitsConstraint,
    ShipmentMinimizationConstraint,
)
from src.orchestrator.services.sql_server_db import DBConnectionFactory, SQLExecutor
from src.orchestrator.ui.terminal_ui import (
    Colors,
    print_header,
    print_success,
    print_error,
    print_warning,
    print_info,
    print_action,
    print_menu_item,
    print_prompt,
    colorize
)


def configure_dates() -> dict:
    """Configure snapshot dates."""
    print_header("Date Configuration", Colors.BRIGHT_BLUE)
    
    # Snapshot date
    print_info("\nSnapshot Date:")
    print(colorize("  - Press Enter to use today's date", Colors.DIM))
    print(colorize("  - Enter a date (YYYY-MM-DD) to use a specific date", Colors.DIM))
    snapshot_date_str = print_prompt("Enter snapshot date (YYYY-MM-DD) or press Enter for today: ").strip()
    
    snapshot_date = None
    if snapshot_date_str:
        try:
            snapshot_date = date.fromisoformat(snapshot_date_str)
        except ValueError:
            print_error("Invalid date format. Using today's date.")
            snapshot_date = None
    
    if snapshot_date is None:
        snapshot_date = date.today()
        print_info(f"Using today's date: {snapshot_date}")
    
    # Snapshot month (optional)
    # print_info("\nSnapshot Month (for sales data):")
    # print(colorize("  - Press Enter to use snapshot date's month", Colors.DIM))
    # print(colorize("  - Enter a date (YYYY-MM-DD) to use a specific month", Colors.DIM))
    # snapshot_month_str = print_prompt("Enter snapshot month (YYYY-MM-DD) or press Enter: ").strip()
    
    # snapshot_month = None
    # if snapshot_month_str:
    #     try:
    #         snapshot_month = date.fromisoformat(snapshot_month_str)
    #     except ValueError:
    #         print_error("Invalid date format. Using snapshot date's month.")
    #         snapshot_month = None
    
    return {
        'snapshot_date': snapshot_date,
        'snapshot_month': None
    }


def configure_database() -> dict:
    # """Configure database settings."""
    # print_header("Database Configuration", Colors.BRIGHT_BLUE)
    
    # # Database type
    # print_info("\nDatabase Type:")
    # print_menu_item('1', 'Test database', Colors.BRIGHT_WHITE)
    # print_menu_item('2', 'Source database', Colors.WHITE)
    # db_choice = print_prompt("Select database type (1/2, default=1): ").strip() or "1"
    
    # database_type = 'source' if db_choice == "2" else 'test'
    
    # Config path (optional)
    # print_info("\nDatabase Configuration File:")
    # print(colorize("  - Press Enter to use default configuration", Colors.DIM))
    # print(colorize("  - Enter path to custom YAML configuration file", Colors.DIM))
    # config_path_str = print_prompt("Enter config path (optional): ").strip()
    
    # config_path = config_path_str if config_path_str else None
    
    return {
        'database_type': 'test',
        'config_path': None
    }


def configure_optimization_settings() -> OptimizationSettings:
    """Configure optimization parameters."""
    print_header("Optimization Settings", Colors.BRIGHT_BLUE)

    settings = OptimizationSettings()

    print_info("\nCurrent Optimization Parameters:")
    print(colorize(f"  - coverage_ratio: {settings.coverage_ratio}", Colors.WHITE))
    print(colorize(f"  - target_coverage_ratio: {settings.target_coverage_ratio}", Colors.WHITE))
    print(colorize(f"  - sales_window: {settings.sales_window} months", Colors.WHITE))
    print(colorize(f"  - delivery_lower_bound: {settings.delivery_lower_bound}", Colors.WHITE))
    print(colorize(f"  - delivery_upper_bound: {settings.delivery_upper_bound}", Colors.WHITE))
    print(colorize(f"  - weight_coverage: {settings.weight_coverage}", Colors.WHITE))
    print(colorize(f"  - weight_target_units: {settings.weight_target_units}", Colors.WHITE))
    print(colorize(f"  - weight_smoothing: {settings.weight_smoothing}", Colors.WHITE))
    print(colorize(f"  - weight_shipment: {settings.weight_shipment}", Colors.WHITE))
    print(colorize("  (Press Enter to edit; type 'n' to keep these and skip editing)", Colors.DIM))

    edit_choice = print_prompt("Edit these settings? (y/n, default=y): ").strip().lower()
    if edit_choice in {"n", "no"}:
        return settings

    def prompt_float(label: str, current: float, hint: Optional[str] = None) -> float:
        if hint:
            print(colorize(f"  - {hint}", Colors.DIM))
        value_str = print_prompt(f"{label} (current: {current}): ").strip()
        if not value_str:
            return current
        try:
            return float(value_str)
        except ValueError:
            print_error("Invalid number. Keeping current value.")
            return current

    def prompt_int(label: str, current: int, hint: Optional[str] = None) -> int:
        if hint:
            print(colorize(f"  - {hint}", Colors.DIM))
        value_str = print_prompt(f"{label} (current: {current}): ").strip()
        if not value_str:
            return current
        try:
            return int(value_str)
        except ValueError:
            print_error("Invalid number. Keeping current value.")
            return current

    print_info("\nEdit Optimization Parameters:")
    coverage_ratio = prompt_float(
        "Distributor coverage ratio",
        settings.coverage_ratio,
        "Multiplier for distributor-product coverage (SC1) (e.g., 1.5 = 150% of demand)",
    )
    target_coverage_ratio = prompt_float(
        "Target units coverage ratio",
        settings.target_coverage_ratio,
        "Multiplier for target units coverage (SC2) (e.g., 1.5 = 150% of target)",
    )
    sales_window = prompt_int(
        "Sales moving average window (months)",
        settings.sales_window,
        "Allowed values: 3 or 6",
    )
    if sales_window not in {3, 6}:
        print_warning("Unsupported sales window. Keeping current value.")
        sales_window = settings.sales_window

    delivery_lower_bound = prompt_float(
        "Delivery lower bound",
        settings.delivery_lower_bound,
        "Lower bound for delivery smoothing constraint (e.g., 0.9 = 90%)",
    )
    delivery_upper_bound = prompt_float(
        "Delivery upper bound",
        settings.delivery_upper_bound,
        "Upper bound for delivery smoothing constraint (e.g., 1.2 = 120%)",
    )
    if delivery_lower_bound > delivery_upper_bound:
        print_warning("Lower bound exceeds upper bound. Keeping current values.")
        delivery_lower_bound = settings.delivery_lower_bound
        delivery_upper_bound = settings.delivery_upper_bound

    weight_coverage = prompt_float(
        "Coverage slack weight",
        settings.weight_coverage,
        "Weight for coverage constraint violations in objective",
    )
    weight_target_units = prompt_float(
        "Target units slack weight",
        settings.weight_target_units,
        "Weight for target units constraint violations in objective",
    )
    weight_smoothing = prompt_float(
        "Delivery smoothing weight",
        settings.weight_smoothing,
        "Weight for delivery smoothing constraint violations in objective",
    )
    weight_shipment = prompt_float(
        "Shipment weight",
        settings.weight_shipment,
        "Weight for decision variables in objective (penalizes unnecessary shipping)",
    )

    return OptimizationSettings(
        coverage_ratio=coverage_ratio,
        target_coverage_ratio=target_coverage_ratio,
        sales_window=sales_window,
        delivery_lower_bound=delivery_lower_bound,
        delivery_upper_bound=delivery_upper_bound,
        weight_coverage=weight_coverage,
        weight_target_units=weight_target_units,
        weight_smoothing=weight_smoothing,
        weight_shipment=weight_shipment,
    )


def configure_solver() -> str:
    """Configure solver selection (priority order: exact LP first, then heuristics)."""
    print_header("Solver Configuration", Colors.BRIGHT_BLUE)
    available = get_available_solver_names()

    def solver_desc(name: str, desc: str) -> str:
        if name in available:
            return desc
        return f"{desc} [not available]"

    labels = {
        "CBC": "CBC (Coin-or Branch and Cut) - Recommended",
        "GLPK": "GLPK (GNU Linear Programming Kit)",
        "Scipy": "Scipy (HiGHS) - exact LP, no PuLP",
        "Greedy": "Greedy - heuristic baseline, fast",
        "SimulatedAnnealing": "Simulated Annealing - metaheuristic",
    }
    print_info("\nSelect Solver (priority order for evaluation):")
    solver_map = {}
    for i, name in enumerate(SOLVER_PRIORITY, start=1):
        desc = labels.get(name, name)
        print_menu_item(
            str(i),
            solver_desc(name, desc),
            Colors.BRIGHT_WHITE if name in available else Colors.DIM,
        )
        solver_map[str(i)] = name
    default = "1"
    prompt = f"Select solver (1-{len(SOLVER_PRIORITY)}, default={default}): "
    solver_choice = print_prompt(prompt).strip() or default
    return solver_map.get(solver_choice, SOLVER_PRIORITY[0])


def configure_output(snapshot_date: date, solver_name: str) -> dict[str, Any]:
    """Configure output files: save JSON (and optionally CSV) into the project data directory.
    Default filename uses optimization date (YYYYMMDD) and solver name."""
    print_header("Output Configuration", Colors.BRIGHT_BLUE)

    project_root = Path(__file__).resolve().parent.parent
    data_dir = project_root / "data"
    date_str = snapshot_date.strftime("%Y%m%d")
    default_json_path = data_dir / f"optimization_results_{date_str}_{solver_name}.json"
    default_csv_path = data_dir / f"optimization_results_{date_str}_{solver_name}.csv"

    print_info("\nSave Results to File (JSON):")
    print(colorize(f"  - Results will be saved to: {default_json_path}", Colors.DIM))
    print(colorize("  - Press Enter to use the default path above", Colors.DIM))
    print(colorize("  - Enter a filename (e.g. my_run.json) to save under data/ with that name", Colors.DIM))
    user_input = print_prompt("Enter filename (optional, or Enter for default): ").strip()

    if user_input:
        name = user_input if user_input.endswith(".json") else f"{user_input}.json"
        output_file = data_dir / name
    else:
        output_file = default_json_path

    csv_file: Optional[str] = None
    csv_include_variables = False
    print_info("\nSave results to CSV:")
    print(colorize("  - Enter 'y' to also save a CSV file (distributor, product, quantity)", Colors.DIM))
    csv_choice = print_prompt("Save CSV as well? (y/n, default=n): ").strip().lower()
    if csv_choice in ("y", "yes"):
        csv_base = output_file.stem
        csv_file = str(data_dir / f"{csv_base}.csv")
        print_info("\nInclude optimization input variables in CSV:")
        print(colorize("  - Adds columns: distributor_inventory, sales_ma, sales_mtd, coverage_demand, delivery_ma_6, has_delivery_last_6m, target_units, factory_supply", Colors.DIM))
        var_choice = print_prompt("Include input variables in CSV? (y/n, default=n): ").strip().lower()
        csv_include_variables = var_choice in ("y", "yes")

    return {
        "output_file": str(output_file),
        "csv_file": csv_file,
        "csv_include_variables": csv_include_variables,
    }


def initialize_database(config_path: Optional[str] = None) -> SQLExecutor:
    """Initialize database connection and SQL executor."""
    print_action("Initializing database connection...")
    
    try:
        if config_path:
            factory = DBConnectionFactory.from_config_file(Path(config_path))
            print_info(f"Loaded database config from: {config_path}")
        else:
            factory = DBConnectionFactory()
            print_info("Using default database configuration")
        
        sql_executor = SQLExecutor(factory)
        print_success("Database connection initialized successfully")
        return sql_executor
    except Exception as e:
        print_error(f"Failed to initialize database: {e}")
        raise


def load_optimization_data(
    sql_executor: SQLExecutor,
    snapshot_date: date,
    snapshot_month: Optional[date],
    database_type: str,
    settings: OptimizationSettings
):
    """Load optimization data from database."""
    print_action(f"Loading optimization data from {database_type} database...")
    print_info(f"Snapshot date: {snapshot_date}")
    if snapshot_month:
        print_info(f"Snapshot month: {snapshot_month}")
    
    try:
        loader = SnapshotDataLoader(
            sql_executor=sql_executor,
            database_type=database_type
        )
        
        data = loader.load_optimization_data(
            snapshot_date=snapshot_date,
            snapshot_month=snapshot_month,
            settings=settings
        )
        
        print_success(f"Loaded data: {len(data.distributors)} distributors, {len(data.products)} products")
        return data
    except Exception as e:
        print_error(f"Failed to load optimization data: {e}")
        raise


def build_and_solve_model(data, solver_name: str, settings=None):
    """Build optimization model and solve. Pass settings to force their use in the model."""
    print_action("Building optimization model...")
    
    # Define constraints
    constraints = [
        FactorySupplyConstraint(),            # Hard: factory capacity
        DeliveryHistoryConstraint(),          # Hard: no delivery without history
        DeliverySmoothingConstraint(),        # Soft: delivery smoothing
        DemandCoverageConstraint(),      # Soft: demand coverage
        ProductTargetUnitsConstraint(),       # Soft: product targets
        ShipmentMinimizationConstraint(),     # Soft: penalize unnecessary shipment
    ]
    
    constraint_names = [c.__class__.__name__ for c in constraints]
    print_info(f"Constraints: {', '.join(constraint_names)}")
    
    # Build model (settings_override ensures CLI parameters are used in the optimization layer)
    builder = ModelBuilder(constraints)
    result = builder.build(data, settings_override=settings)
    
    print_success(f"Model built: {len(result.decision_variables)} decision variables, "
                  f"{len(result.model.constraints)} constraints, "
                  f"{len(result.slack_variables)} slack variables")
    
    # Solve
    print_action(f"Solving optimization problem with {solver_name} solver...")
    try:
        solution = solve(
            result.model,
            result.decision_variables,
            method=solver_name,
            data=data,
        )
        print_success(f"Solution status: {solution.status}")
        return result, solution
    except ValueError as e:
        print_error(f"Configuration error: {e}")
        raise
    except ImportError as e:
        print_error(f"Solver not available: {e}")
        print_error("For LP: pip install pulp  |  For Scipy: pip install scipy")
        raise
    except Exception as e:
        print_error(f"Solver error: {e}")
        raise


def _distributor_label(data, distributor_id: str) -> str:
    """Display name for distributor (from dimension) or ID if name not available."""
    return (data.distributor_names or {}).get(distributor_id, distributor_id)


def _product_label(data, product_id: str) -> str:
    """Display name for product (from dimension) or ID if name not available."""
    return (data.product_names or {}).get(product_id, product_id)


def format_results(result, solution, data) -> dict:
    """Format results as dictionary. Uses distributor and product names from dimensions when available."""
    # Extract shipment quantities; use names for output when available
    shipments = {}
    for (distributor_id, product_id), variable in result.decision_variables.items():
        quantity = solution.variable_values.get(variable, 0.0)
        shipments[f"{distributor_id}_{product_id}"] = {
            "distributor": _distributor_label(data, distributor_id),
            "product": _product_label(data, product_id),
            "quantity": round(quantity, 2),
        }
    total_shipments = sum(
        solution.variable_values.get(variable, 0.0)
        for variable in result.decision_variables.values()
    )
    # Group by product name (or ID) for summary
    shipments_by_product: dict[str, float] = {}
    for (distributor_id, product_id), variable in result.decision_variables.items():
        quantity = solution.variable_values.get(variable, 0.0)
        key = _product_label(data, product_id)
        shipments_by_product[key] = shipments_by_product.get(key, 0.0) + quantity
    shipments_by_distributor: dict[str, float] = {}
    for (distributor_id, product_id), variable in result.decision_variables.items():
        quantity = solution.variable_values.get(variable, 0.0)
        key = _distributor_label(data, distributor_id)
        shipments_by_distributor[key] = shipments_by_distributor.get(key, 0.0) + quantity
    return {
        "status": solution.status,
        "is_optimal": solution.is_optimal,
        "is_feasible": solution.is_feasible,
        "objective_value": round(solution.objective_value, 2) if solution.objective_value else None,
        "solver_name": solution.solver_name,
        "summary": {
            "total_shipments": round(total_shipments, 2),
            "num_distributors": len(data.distributors),
            "num_products": len(data.products),
            "shipments_by_product": {k: round(v, 2) for k, v in shipments_by_product.items()},
            "shipments_by_distributor": {k: round(v, 2) for k, v in shipments_by_distributor.items()},
        },
        "shipments": list(shipments.values()),
    }


def save_results(results: dict, output_file: str):
    """Save results to JSON file."""
    output_path = Path(output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_path, 'w') as f:
        json.dump(results, f, indent=2)
    
    print_success(f"Results saved to: {output_path}")


def save_results_csv(result, solution, data, csv_path: str, include_variables: bool = False):
    """Save optimization results to CSV. Optionally include input variables per (distributor, product)."""
    output_path = Path(csv_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

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

    with open(output_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print_success(f"CSV results saved to: {output_path}")


def run_optimization(config: dict):
    """Run the optimization with provided configuration."""
    print_header("Running Optimization", Colors.BRIGHT_GREEN)
    
    try:
        # Initialize database
        sql_executor = initialize_database(config.get('config_path'))
        
        # Load data
        data = load_optimization_data(
            sql_executor=sql_executor,
            snapshot_date=config['snapshot_date'],
            snapshot_month=config.get('snapshot_month'),
            database_type=config['database_type'],
            settings=config['settings']
        )

        # Confirm settings used (so parameter changes are visible)
        s = config["settings"]
        print_info(
            f"Settings for this run: coverage_ratio={s.coverage_ratio}, target_coverage_ratio={s.target_coverage_ratio}, sales_window={s.sales_window}, "
            f"delivery_bounds=[{s.delivery_lower_bound}, {s.delivery_upper_bound}], "
            f"weights=(coverage={s.weight_coverage}, target_units={s.weight_target_units}, smoothing={s.weight_smoothing})"
        )
        
        # Build and solve (pass settings so optimization layer uses CLI parameters)
        result, solution = build_and_solve_model(
            data, config['solver'], settings=config['settings']
        )
        
        # Format results
        results = format_results(result, solution, data)
        
        # Save results if requested
        if config.get('output_file'):
            save_results(results, config['output_file'])
        if config.get('csv_file'):
            save_results_csv(
                result,
                solution,
                data,
                config['csv_file'],
                include_variables=config.get('csv_include_variables', False),
            )

        print_success("Optimization completed successfully")
        
        # Warn if solution is not optimal/feasible
        if not solution.is_feasible:
            print_warning("Solution is not feasible - check constraints and data")
            return False
        elif not solution.is_optimal:
            print_warning("Solution is feasible but not proven optimal")
            return True
        else:
            return True
            
    except Exception as e:
        print_error(f"Optimization failed: {e}")
        raise


def main():
    """Main interactive CLI function."""
    print_header("Optimization CLI - Production", Colors.BRIGHT_CYAN)
    
    while True:
        try:
            # Configure all parameters
            date_config = configure_dates()
            db_config = configure_database()
            settings = configure_optimization_settings()
            solver = configure_solver()
            output_config = configure_output(
                snapshot_date=date_config["snapshot_date"],
                solver_name=solver,
            )
            output_file = output_config["output_file"]
            csv_file = output_config.get("csv_file")
            csv_include_variables = output_config.get("csv_include_variables", False)

            # Summary
            print_header("Configuration Summary", Colors.BRIGHT_CYAN)
            print_info(f"Snapshot Date: {date_config['snapshot_date']}")
            if date_config.get('snapshot_month'):
                print_info(f"Snapshot Month: {date_config['snapshot_month']}")
            print_info(f"Database Type: {db_config['database_type']}")
            print_info(f"Distributor Coverage Ratio: {settings.coverage_ratio}")
            print_info(f"Target Coverage Ratio: {settings.target_coverage_ratio}")
            print_info(f"Sales Window: {settings.sales_window} months")
            print_info(f"Coverage Weight: {settings.weight_coverage}")
            print_info(f"Target Units Weight: {settings.weight_target_units}")
            print_info(f"Solver: {solver}")
            if output_file:
                print_info(f"Output File (JSON): {output_file}")
            if csv_file:
                print_info(f"Output File (CSV): {csv_file}")
                if csv_include_variables:
                    print_info("  CSV will include optimization input variables")
            
            # Confirm
            confirm = print_prompt("\nProceed with optimization? (y/n, default=y): ").strip().lower()
            if confirm == 'n':
                print_info("Cancelled by user.")
                break
            
            # Combine configuration
            config = {
                **date_config,
                **db_config,
                'settings': settings,
                'solver': solver,
                'output_file': output_file,
                'csv_file': csv_file,
                'csv_include_variables': csv_include_variables,
            }
            
            # Run optimization
            success = run_optimization(config)
            
            # Ask if user wants to run again
            if success:
                continue_choice = print_prompt("\nRun another optimization? (y/n, default=n): ").strip().lower()
                if continue_choice != 'y':
                    break
            else:
                continue_choice = print_prompt("\nTry again with different settings? (y/n, default=y): ").strip().lower()
                if continue_choice != 'y':
                    break
                    
        except KeyboardInterrupt:
            print()
            print_warning("Interrupted by user.")
            break
        except Exception as e:
            print_error(f"Error: {str(e)}")
            import traceback
            traceback.print_exc()
            continue_choice = print_prompt("\nTry again? (y/n, default=y): ").strip().lower()
            if continue_choice != 'y':
                break
    
    print()
    print_info("Goodbye!")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print()
        print()
        print_warning("Interrupted by user. Goodbye!")
        sys.exit(0)

