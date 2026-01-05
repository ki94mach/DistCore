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

import json
import sys
from datetime import date
from pathlib import Path
from typing import Optional

# Add project root to Python path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.optimization import (
    OptimizationSettings,
    ModelBuilder,
    solve_with_pulp,
    SnapshotDataLoader
)
from src.optimization.constraints import (
    FactorySupplyConstraint,
    DistributorCoverageConstraint,
    ProductTargetUnitsConstraint
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
    print_info("\nSnapshot Month (for sales data):")
    print(colorize("  - Press Enter to use snapshot date's month", Colors.DIM))
    print(colorize("  - Enter a date (YYYY-MM-DD) to use a specific month", Colors.DIM))
    snapshot_month_str = print_prompt("Enter snapshot month (YYYY-MM-DD) or press Enter: ").strip()
    
    snapshot_month = None
    if snapshot_month_str:
        try:
            snapshot_month = date.fromisoformat(snapshot_month_str)
        except ValueError:
            print_error("Invalid date format. Using snapshot date's month.")
            snapshot_month = None
    
    return {
        'snapshot_date': snapshot_date,
        'snapshot_month': snapshot_month
    }


def configure_database() -> dict:
    """Configure database settings."""
    print_header("Database Configuration", Colors.BRIGHT_BLUE)
    
    # Database type
    print_info("\nDatabase Type:")
    print_menu_item('1', 'Test database', Colors.BRIGHT_WHITE)
    print_menu_item('2', 'Source database', Colors.WHITE)
    db_choice = print_prompt("Select database type (1/2, default=1): ").strip() or "1"
    
    database_type = 'source' if db_choice == "2" else 'test'
    
    # Config path (optional)
    print_info("\nDatabase Configuration File:")
    print(colorize("  - Press Enter to use default configuration", Colors.DIM))
    print(colorize("  - Enter path to custom YAML configuration file", Colors.DIM))
    config_path_str = print_prompt("Enter config path (optional): ").strip()
    
    config_path = config_path_str if config_path_str else None
    
    return {
        'database_type': database_type,
        'config_path': config_path
    }


def configure_optimization_settings() -> OptimizationSettings:
    """Configure optimization parameters."""
    print_header("Optimization Settings", Colors.BRIGHT_BLUE)
    
    # Coverage ratio
    print_info("\nCoverage Ratio:")
    print(colorize("  - Multiplier for target coverage (e.g., 1.5 = 150% of demand)", Colors.DIM))
    coverage_ratio_str = print_prompt("Enter coverage ratio (default: 1.5): ").strip()
    try:
        coverage_ratio = float(coverage_ratio_str) if coverage_ratio_str else 1.5
    except ValueError:
        print_error("Invalid number. Using default 1.5.")
        coverage_ratio = 1.5
    
    # Sales window
    print_info("\nSales Moving Average Window:")
    print_menu_item('1', '3 months', Colors.BRIGHT_WHITE)
    print_menu_item('2', '6 months (recommended)', Colors.WHITE)
    window_choice = print_prompt("Select window (1/2, default=2): ").strip() or "2"
    sales_window = 3 if window_choice == "1" else 6
    
    # Weight coverage
    print_info("\nCoverage Slack Weight:")
    print(colorize("  - Weight for coverage constraint violations in objective", Colors.DIM))
    weight_coverage_str = print_prompt("Enter weight (default: 1.0): ").strip()
    try:
        weight_coverage = float(weight_coverage_str) if weight_coverage_str else 1.0
    except ValueError:
        print_error("Invalid number. Using default 1.0.")
        weight_coverage = 1.0
    
    # Weight target units
    print_info("\nTarget Units Slack Weight:")
    print(colorize("  - Weight for target units constraint violations in objective", Colors.DIM))
    weight_target_str = print_prompt("Enter weight (default: 2.0): ").strip()
    try:
        weight_target_units = float(weight_target_str) if weight_target_str else 2.0
    except ValueError:
        print_error("Invalid number. Using default 2.0.")
        weight_target_units = 2.0
    
    return OptimizationSettings(
        coverage_ratio=coverage_ratio,
        sales_window=sales_window,
        weight_coverage=weight_coverage,
        weight_target_units=weight_target_units
    )


def configure_solver() -> str:
    """Configure solver selection."""
    print_header("Solver Configuration", Colors.BRIGHT_BLUE)
    
    print_info("\nSelect Solver:")
    print_menu_item('1', 'CBC (Coin-or Branch and Cut) - Recommended', Colors.BRIGHT_WHITE)
    print_menu_item('2', 'GLPK (GNU Linear Programming Kit)', Colors.WHITE)
    print_menu_item('3', 'CPLEX (IBM - requires license)', Colors.WHITE)
    print_menu_item('4', 'GUROBI (requires license)', Colors.WHITE)
    
    solver_choice = print_prompt("Select solver (1/2/3/4, default=1): ").strip() or "1"
    
    solver_map = {
        '1': 'CBC',
        '2': 'GLPK',
        '3': 'CPLEX',
        '4': 'GUROBI'
    }
    
    return solver_map.get(solver_choice, 'CBC')


def configure_output() -> Optional[str]:
    """Configure output file."""
    print_header("Output Configuration", Colors.BRIGHT_BLUE)
    
    print_info("\nSave Results to File:")
    print(colorize("  - Press Enter to skip saving to file", Colors.DIM))
    print(colorize("  - Enter path to save results as JSON", Colors.DIM))
    output_file = print_prompt("Enter output file path (optional): ").strip()
    
    return output_file if output_file else None


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


def build_and_solve_model(data, solver_name: str):
    """Build optimization model and solve."""
    print_action("Building optimization model...")
    
    # Define constraints
    constraints = [
        FactorySupplyConstraint(),      # Hard: factory capacity
        DistributorCoverageConstraint(), # Soft: distributor coverage
        ProductTargetUnitsConstraint()   # Soft: product targets
    ]
    
    constraint_names = [c.__class__.__name__ for c in constraints]
    print_info(f"Constraints: {', '.join(constraint_names)}")
    
    # Build model
    builder = ModelBuilder(constraints)
    result = builder.build(data)
    
    print_success(f"Model built: {len(result.decision_variables)} decision variables, "
                  f"{len(result.model.constraints)} constraints, "
                  f"{len(result.slack_variables)} slack variables")
    
    # Solve
    print_action(f"Solving optimization problem with {solver_name} solver...")
    try:
        solution = solve_with_pulp(
            result.model,
            result.decision_variables,
            solver_name=solver_name
        )
        print_success(f"Solution status: {solution.status}")
        return result, solution
    except ImportError as e:
        print_error(f"PuLP solver not available: {e}")
        print_error("Install PuLP: pip install pulp")
        raise
    except Exception as e:
        print_error(f"Solver error: {e}")
        raise


def format_results(result, solution, data) -> dict:
    """Format results as dictionary."""
    # Extract shipment quantities
    shipments = {}
    for (distributor, product), variable in result.decision_variables.items():
        quantity = solution.variable_values.get(variable, 0.0)
        shipments[f"{distributor}_{product}"] = {
            "distributor": distributor,
            "product": product,
            "quantity": round(quantity, 2)
        }
    
    # Calculate summary statistics
    total_shipments = sum(
        solution.variable_values.get(variable, 0.0)
        for variable in result.decision_variables.values()
    )
    
    # Group by product
    shipments_by_product = {}
    for (distributor, product), variable in result.decision_variables.items():
        quantity = solution.variable_values.get(variable, 0.0)
        if product not in shipments_by_product:
            shipments_by_product[product] = 0.0
        shipments_by_product[product] += quantity
    
    # Group by distributor
    shipments_by_distributor = {}
    for (distributor, product), variable in result.decision_variables.items():
        quantity = solution.variable_values.get(variable, 0.0)
        if distributor not in shipments_by_distributor:
            shipments_by_distributor[distributor] = 0.0
        shipments_by_distributor[distributor] += quantity
    
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
        "shipments": list(shipments.values())
    }


def print_results(results: dict):
    """Print results to console."""
    print_header("OPTIMIZATION RESULTS", Colors.BRIGHT_GREEN)
    
    # Status information
    status_color = Colors.BRIGHT_GREEN if results['is_optimal'] else (Colors.YELLOW if results['is_feasible'] else Colors.RED)
    print_info(f"Status: {colorize(results['status'], status_color)}")
    print_info(f"Optimal: {colorize(str(results['is_optimal']), status_color)}")
    print_info(f"Feasible: {colorize(str(results['is_feasible']), status_color)}")
    if results['objective_value'] is not None:
        print_info(f"Objective Value: {colorize(str(results['objective_value']), Colors.BRIGHT_WHITE)}")
    print_info(f"Solver: {results['solver_name']}")
    
    summary = results['summary']
    print_info(f"\nSummary:")
    print_info(f"  Total Shipments: {colorize(str(summary['total_shipments']), Colors.BRIGHT_WHITE)}")
    print_info(f"  Distributors: {summary['num_distributors']}")
    print_info(f"  Products: {summary['num_products']}")
    
    print_info(f"\nShipments by Product:")
    for product, qty in summary['shipments_by_product'].items():
        print_info(f"  {product}: {colorize(str(qty), Colors.BRIGHT_WHITE)}")
    
    print_info(f"\nShipments by Distributor:")
    for distributor, qty in summary['shipments_by_distributor'].items():
        print_info(f"  {distributor}: {colorize(str(qty), Colors.BRIGHT_WHITE)}")
    
    print_info(f"\nDetailed Shipments:")
    print(colorize(f"{'Distributor':<20} {'Product':<15} {'Quantity':>15}", Colors.DIM))
    print(colorize("-" * 70, Colors.DIM))
    for shipment in sorted(results['shipments'], key=lambda x: (x['distributor'], x['product'])):
        print_info(f"{shipment['distributor']:<20} {shipment['product']:<15} {shipment['quantity']:>15.2f}")


def save_results(results: dict, output_file: str):
    """Save results to JSON file."""
    output_path = Path(output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_path, 'w') as f:
        json.dump(results, f, indent=2)
    
    print_success(f"Results saved to: {output_path}")


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
        
        # Build and solve
        result, solution = build_and_solve_model(data, config['solver'])
        
        # Format results
        results = format_results(result, solution, data)
        
        # Print results
        print_results(results)
        
        # Save results if requested
        if config.get('output_file'):
            save_results(results, config['output_file'])
        
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
            output_file = configure_output()
            
            # Summary
            print_header("Configuration Summary", Colors.BRIGHT_CYAN)
            print_info(f"Snapshot Date: {date_config['snapshot_date']}")
            if date_config.get('snapshot_month'):
                print_info(f"Snapshot Month: {date_config['snapshot_month']}")
            print_info(f"Database Type: {db_config['database_type']}")
            print_info(f"Coverage Ratio: {settings.coverage_ratio}")
            print_info(f"Sales Window: {settings.sales_window} months")
            print_info(f"Coverage Weight: {settings.weight_coverage}")
            print_info(f"Target Units Weight: {settings.weight_target_units}")
            print_info(f"Solver: {solver}")
            if output_file:
                print_info(f"Output File: {output_file}")
            
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
                'output_file': output_file
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

