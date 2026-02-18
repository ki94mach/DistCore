"""Enhanced visualization tool with line charts for constraints and objective function.

This script creates visualizations showing:
1. Constraint values as functions of shipment quantity (line charts)
2. Objective function value as a function of shipment quantity
3. Feasible region where constraints are satisfied
4. Optimal solution point

Usage:
    # Product-level view (all distributors) - can use product ID or English name
    python scripts/visualize_optimization.py --product P1 --date 2026-02-17
    python scripts/visualize_optimization.py --product "Product Name" --date 2026-02-17
    
    # Distributor-product pair view - can use product ID or English name
    python scripts/visualize_optimization.py --distributor D1 --product P1 --date 2026-02-17
    python scripts/visualize_optimization.py --distributor D1 --product "Product Name" --date 2026-02-17
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import matplotlib.pyplot as plt
import numpy as np

# Add project root to Python path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.optimization import (
    OptimizationSettings,
    ModelBuilder,
    solve,
    SnapshotDataLoader,
)
from src.optimization.constraints import (
    DeliveryHistoryConstraint,
    DeliverySmoothingConstraint,
    FactorySupplyConstraint,
    DemandCoverageConstraint,
    ProductTargetUnitsConstraint,
    ShipmentMinimizationConstraint,
)
from src.optimization.solvers import get_default_settings, get_constraint_preset
from src.orchestrator.services.sql_server_db import DBConnectionFactory, SQLExecutor
from src.orchestrator.ui.terminal_ui import (
    Colors,
    print_header,
    print_success,
    print_error,
    print_info,
    print_action,
    print_warning,
)


class EnhancedOptimizationVisualizer:
    """Enhanced visualizer with line charts for constraints and objective function."""

    def __init__(
        self,
        distributor_id: Optional[str],
        product_id: str,
        data: Any,
        result: Any,
        solution: Any,
        settings: OptimizationSettings,
    ):
        self.distributor_id = distributor_id
        self.product_id = product_id
        self.data = data
        self.result = result
        self.solution = solution
        self.settings = settings

    def extract_constraint_info(self) -> Dict[str, Any]:
        """Extract constraint information."""
        info = {
            "decision_variable": None,
            "decision_value": 0.0,
            "constraints": [],
            "slack_variables": {},
            "data_values": {},
            "objective_coefficients": {},
        }

        if self.distributor_id:
            # Distributor-product pair view
            key = (self.distributor_id, self.product_id)
            if key in self.result.decision_variables:
                var = self.result.decision_variables[key]
                info["decision_variable"] = var
                info["decision_value"] = self.solution.variable_values.get(var, 0.0)

            # Extract data values
            info["data_values"] = {
                "inventory": self.data.inventory(self.distributor_id, self.product_id),
                "demand": self.data.coverage_demand(self.distributor_id, self.product_id),
                "demand_target": (
                    self.settings.coverage_ratio
                    * self.data.coverage_demand(self.distributor_id, self.product_id)
                ),
                "delivery_ma": self.data.delivery_moving_average(
                    self.distributor_id, self.product_id
                ),
                "delivery_lower_bound": (
                    self.settings.delivery_lower_bound
                    * self.data.delivery_moving_average(self.distributor_id, self.product_id)
                ),
                "delivery_upper_bound": (
                    self.settings.delivery_upper_bound
                    * self.data.delivery_moving_average(self.distributor_id, self.product_id)
                ),
                "factory_supply": self.data.factory_supply(self.product_id),
                "has_delivery_history": self.data.has_recent_delivery(
                    self.distributor_id, self.product_id
                ),
            }

            # Extract constraints
            for constraint in self.result.model.constraints:
                constraint_name = constraint.name
                if (
                    self.distributor_id in constraint_name
                    and self.product_id in constraint_name
                ) or (
                    constraint_name.startswith("factory_supply_")
                    and constraint_name.endswith(f"_{self.product_id}")
                ):
                    var_involved = (
                        info["decision_variable"] in constraint.expression.coefficients
                        if info["decision_variable"]
                        else False
                    )

                    if var_involved or constraint_name.startswith("factory_supply_"):
                        constraint_info = {
                            "name": constraint_name,
                            "sense": constraint.sense,
                            "rhs": constraint.rhs,
                            "coefficients": {
                                var.name: coeff
                                for var, coeff in constraint.expression.coefficients.items()
                            },
                            "constant": constraint.expression.constant,
                        }
                        info["constraints"].append(constraint_info)

            # Extract slack variables
            for slack_var in self.result.slack_variables:
                if (
                    self.distributor_id in slack_var.name
                    and self.product_id in slack_var.name
                ):
                    info["slack_variables"][slack_var.name] = self.solution.variable_values.get(
                        slack_var, 0.0
                    )

        # Extract objective coefficients
        if self.result.model.objective:
            for var, coeff in self.result.model.objective.expression.coefficients.items():
                info["objective_coefficients"][var.name] = coeff

        return info

    def evaluate_constraint_at_x(
        self, constraint_info: Dict[str, Any], x_value: float, slack_values: Dict[str, float]
    ) -> float:
        """Evaluate constraint LHS at a given x value."""
        lhs = constraint_info["constant"]
        
        # Add decision variable contribution
        if self.distributor_id:
            var_name = f"x_{self.distributor_id}_{self.product_id}"
            if var_name in constraint_info["coefficients"]:
                lhs += constraint_info["coefficients"][var_name] * x_value
        
        # Add slack variable contributions (use optimal slack values)
        for var_name, coeff in constraint_info["coefficients"].items():
            if var_name.startswith("s_") and var_name in slack_values:
                lhs += coeff * slack_values[var_name]
        
        return lhs

    def evaluate_objective_at_x(
        self, x_value: float, slack_values: Dict[str, float]
    ) -> float:
        """Evaluate objective function at a given x value."""
        if not self.result.model.objective:
            return 0.0
        
        obj_value = self.result.model.objective.expression.constant
        
        # Add decision variable contribution
        if self.distributor_id:
            var_name = f"x_{self.distributor_id}_{self.product_id}"
            if var_name in self.result.model.objective.expression.coefficients:
                var = next(
                    v for v in self.result.model.variables if v.name == var_name
                )
                coeff = self.result.model.objective.expression.coefficients.get(var, 0.0)
                obj_value += coeff * x_value
        
        # Add slack variable contributions
        for slack_var in self.result.slack_variables:
            if slack_var.name in slack_values:
                coeff = self.result.model.objective.expression.coefficients.get(slack_var, 0.0)
                obj_value += coeff * slack_values[slack_var.name]
        
        return obj_value

    def create_constraint_and_objective_plot(self, output_path: Optional[Path] = None) -> None:
        """Create line charts showing constraints and objective function."""
        info = self.extract_constraint_info()

        if not info["decision_variable"]:
            print_error(
                f"No decision variable found for ({self.distributor_id}, {self.product_id})"
            )
            return

        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 10))

        x_var = info["decision_variable"].name
        x_value = info["decision_value"]
        x_max = max(
            info["data_values"]["factory_supply"],
            info["data_values"]["demand_target"] * 1.5,
            info["data_values"]["delivery_upper_bound"] * 1.5,
            x_value * 1.5,
            100.0,
        )

        # Create x-axis range
        x_range = np.linspace(0, x_max, 500)

        # Get optimal slack values for evaluation
        optimal_slack = info["slack_variables"].copy()

        # Top plot: Constraints as line charts
        constraint_lines = []

        # Factory supply constraint: x <= factory_supply
        factory_supply = info["data_values"]["factory_supply"]
        factory_lhs = np.full_like(x_range, factory_supply)  # Constant line at RHS
        ax1.plot(
            x_range,
            factory_lhs,
            "r--",
            linewidth=2,
            label=f"Factory Supply Limit: {factory_supply:.1f}",
            alpha=0.7,
        )
        # Show feasible region (below the line)
        ax1.fill_between(
            x_range,
            0,
            factory_lhs,
            where=(x_range <= factory_supply),
            alpha=0.1,
            color="red",
        )

        # Demand coverage constraint: x + inventory + slack >= demand_target
        demand_target = info["data_values"]["demand_target"]
        inventory = info["data_values"]["inventory"]
        # LHS = x + inventory (assuming slack adjusts)
        demand_lhs = x_range + inventory
        ax1.plot(
            x_range,
            demand_lhs,
            "b-",
            linewidth=2,
            label=f"Demand Coverage LHS: x + {inventory:.1f}",
            alpha=0.7,
        )
        # Show target line
        ax1.axhline(
            y=demand_target,
            color="blue",
            linestyle=":",
            linewidth=2,
            label=f"Demand Target: {demand_target:.1f}",
            alpha=0.7,
        )
        # Show feasible region (above target)
        ax1.fill_between(
            x_range,
            demand_target,
            demand_target + 100,
            where=(demand_lhs >= demand_target),
            alpha=0.1,
            color="blue",
        )

        # Delivery smoothing constraints
        delivery_lower = info["data_values"]["delivery_lower_bound"]
        delivery_upper = info["data_values"]["delivery_upper_bound"]

        if delivery_lower > 0:
            # Lower bound: x >= delivery_lower
            ax1.axvline(
                x=delivery_lower,
                color="green",
                linestyle=":",
                linewidth=2,
                label=f"Delivery Lower Bound: {delivery_lower:.1f}",
                alpha=0.7,
            )

        if delivery_upper > 0:
            # Upper bound: x <= delivery_upper
            ax1.axvline(
                x=delivery_upper,
                color="orange",
                linestyle=":",
                linewidth=2,
                label=f"Delivery Upper Bound: {delivery_upper:.1f}",
                alpha=0.7,
            )

        # Mark optimal solution
        ax1.axvline(
            x=x_value,
            color="purple",
            linestyle="-",
            linewidth=3,
            label=f"Optimal Solution: {x_value:.2f}",
            alpha=0.9,
        )

        # Evaluate constraint values at optimal point
        optimal_demand_lhs = x_value + inventory
        ax1.plot(
            x_value,
            optimal_demand_lhs,
            "o",
            markersize=10,
            color="purple",
            zorder=5,
        )

        ax1.set_xlabel(f"Shipment Quantity: {x_var}", fontsize=12, fontweight="bold")
        ax1.set_ylabel("Constraint Value", fontsize=12)
        ax1.set_title(
            f"Constraints: {self.distributor_id} × {self.product_id}",
            fontsize=14,
            fontweight="bold",
        )
        ax1.legend(loc="upper left", fontsize=9)
        ax1.grid(True, alpha=0.3)
        ax1.set_xlim(0, x_max)
        ax1.set_ylim(0, max(factory_supply, demand_target) * 1.2)

        # Bottom plot: Objective function
        # Evaluate objective at different x values
        # For simplicity, we'll use optimal slack values (this is approximate)
        obj_values = []
        for x in x_range:
            # Calculate slack values that would make constraints feasible at this x
            # This is simplified - in reality slack adjusts to minimize objective
            slack_at_x = optimal_slack.copy()
            
            # Adjust demand slack if needed
            demand_slack_key = f"s_demand_coverage_{self.distributor_id}_{self.product_id}"
            if demand_slack_key in slack_at_x:
                required_demand = demand_target - inventory
                if x < required_demand:
                    slack_at_x[demand_slack_key] = required_demand - x
                else:
                    slack_at_x[demand_slack_key] = 0.0
            
            obj_val = self.evaluate_objective_at_x(x, slack_at_x)
            obj_values.append(obj_val)

        obj_values = np.array(obj_values)
        ax2.plot(
            x_range,
            obj_values,
            "g-",
            linewidth=2,
            label="Objective Function",
            alpha=0.8,
        )

        # Mark optimal point
        optimal_obj = self.evaluate_objective_at_x(x_value, optimal_slack)
        ax2.plot(
            x_value,
            optimal_obj,
            "o",
            markersize=12,
            color="purple",
            label=f"Optimal: ({x_value:.2f}, {optimal_obj:.2f})",
            zorder=5,
        )

        # Add vertical line at optimal
        ax2.axvline(
            x=x_value,
            color="purple",
            linestyle="--",
            linewidth=1.5,
            alpha=0.5,
        )

        ax2.set_xlabel(f"Shipment Quantity: {x_var}", fontsize=12, fontweight="bold")
        ax2.set_ylabel("Objective Value", fontsize=12)
        ax2.set_title(
            f"Objective Function: {self.distributor_id} × {self.product_id}",
            fontsize=14,
            fontweight="bold",
        )
        ax2.legend(loc="upper right", fontsize=9)
        ax2.grid(True, alpha=0.3)
        ax2.set_xlim(0, x_max)

        # Add info boxes
        slack_text = []
        for slack_name, slack_value in info["slack_variables"].items():
            if slack_value > 0.01:
                slack_type = (
                    "demand"
                    if "demand_coverage" in slack_name
                    else "delivery_low"
                    if "delivery_low" in slack_name
                    else "delivery_high"
                    if "delivery_high" in slack_name
                    else "other"
                )
                slack_text.append(f"{slack_type}: {slack_value:.2f}")

        if slack_text:
            ax1.text(
                0.02,
                0.98,
                "Slack Variables:\n" + "\n".join(slack_text),
                transform=ax1.transAxes,
                fontsize=9,
                verticalalignment="top",
                bbox=dict(boxstyle="round", facecolor="wheat", alpha=0.5),
            )

        param_text = (
            f"Parameters:\n"
            f"coverage_ratio = {self.settings.coverage_ratio}\n"
            f"weight_demand = {self.settings.weight_demand}\n"
            f"weight_smoothing = {self.settings.weight_smoothing}\n"
            f"weight_shipment = {self.settings.weight_shipment}"
        )
        ax2.text(
            0.98,
            0.98,
            param_text,
            transform=ax2.transAxes,
            fontsize=9,
            verticalalignment="top",
            horizontalalignment="right",
            bbox=dict(boxstyle="round", facecolor="lightblue", alpha=0.5),
        )

        plt.tight_layout()

        if output_path:
            plt.savefig(output_path, dpi=300, bbox_inches="tight")
            print_success(f"Plot saved to: {output_path}")
        else:
            plt.show()

        plt.close()

    def create_product_level_plot(self, output_path: Optional[Path] = None) -> None:
        """Create product-level visualization with line charts for constraints and objective."""
        # Extract product-level information
        distributors = [
            d for d in self.data.distributors 
            if (d, self.product_id) in self.result.decision_variables
        ]
        
        if not distributors:
            print_error(f"No distributors found for product {self.product_id}")
            return

        # Get product-level data
        factory_supply = self.data.factory_supply(self.product_id)
        target_units = self.data.target_units.get(self.product_id, 0.0)
        remaining_target = self.data.remaining_target_units(self.product_id)
        target_coverage = self.settings.target_coverage_ratio * remaining_target
        
        total_inventory = sum(
            self.data.inventory(d, self.product_id) for d in distributors
        )
        
        # Get optimal shipments
        optimal_shipments = {}
        total_optimal_shipment = 0.0
        for dist_id in distributors:
            key = (dist_id, self.product_id)
            if key in self.result.decision_variables:
                var = self.result.decision_variables[key]
                shipment = self.solution.variable_values.get(var, 0.0)
                optimal_shipments[dist_id] = shipment
                total_optimal_shipment += shipment

        # Get target slack
        target_slack = 0.0
        for slack_var in self.result.slack_variables:
            if slack_var.name == f"s_units_{self.product_id}":
                target_slack = self.solution.variable_values.get(slack_var, 0.0)

        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 10))

        # Create x-axis range (total shipment)
        x_max = max(factory_supply, target_coverage * 1.2, total_optimal_shipment * 1.5, 100.0)
        x_range = np.linspace(0, x_max, 500)

        # Top plot: Product-level constraints
        # Factory supply constraint: total_shipment <= factory_supply
        factory_limit = np.full_like(x_range, factory_supply)
        ax1.plot(
            x_range,
            factory_limit,
            "r--",
            linewidth=2,
            label=f"Factory Supply Limit: {factory_supply:.1f}",
            alpha=0.7,
        )
        # Feasible region (below limit)
        ax1.fill_between(
            x_range,
            0,
            factory_limit,
            where=(x_range <= factory_supply),
            alpha=0.1,
            color="red",
        )

        # Target coverage constraint: total_shipment + total_inventory + slack >= target_coverage
        # LHS = total_shipment + total_inventory
        target_lhs = x_range + total_inventory
        ax1.plot(
            x_range,
            target_lhs,
            "b-",
            linewidth=2,
            label=f"Total Coverage LHS: x + {total_inventory:.1f}",
            alpha=0.7,
        )
        # Target line
        ax1.axhline(
            y=target_coverage,
            color="blue",
            linestyle=":",
            linewidth=2,
            label=f"Target Coverage: {target_coverage:.1f}",
            alpha=0.7,
        )
        # Feasible region (above target)
        ax1.fill_between(
            x_range,
            target_coverage,
            target_coverage + 100,
            where=(target_lhs >= target_coverage),
            alpha=0.1,
            color="blue",
        )

        # Mark optimal total shipment
        optimal_total_coverage = total_optimal_shipment + total_inventory + target_slack
        ax1.axvline(
            x=total_optimal_shipment,
            color="purple",
            linestyle="-",
            linewidth=3,
            label=f"Optimal Total Shipment: {total_optimal_shipment:.2f}",
            alpha=0.9,
        )
        ax1.plot(
            total_optimal_shipment,
            optimal_total_coverage,
            "o",
            markersize=10,
            color="purple",
            zorder=5,
        )

        ax1.set_xlabel("Total Shipment Quantity", fontsize=12, fontweight="bold")
        ax1.set_ylabel("Constraint Value", fontsize=12)
        ax1.set_title(
            f"Product-Level Constraints: {self.product_id}",
            fontsize=14,
            fontweight="bold",
        )
        ax1.legend(loc="upper left", fontsize=9)
        ax1.grid(True, alpha=0.3)
        ax1.set_xlim(0, x_max)
        ax1.set_ylim(0, max(factory_supply, target_coverage) * 1.2)

        # Add distributor allocation info
        dist_text = "Distributor Allocations:\n"
        for dist_id in distributors:
            shipment = optimal_shipments.get(dist_id, 0.0)
            inventory = self.data.inventory(dist_id, self.product_id)
            dist_text += f"{dist_id}: {shipment:.1f} (inv: {inventory:.1f})\n"
        
        if target_slack > 0.01:
            dist_text += f"\nTarget Slack: {target_slack:.2f}"

        ax1.text(
            0.02,
            0.98,
            dist_text,
            transform=ax1.transAxes,
            fontsize=9,
            verticalalignment="top",
            bbox=dict(boxstyle="round", facecolor="wheat", alpha=0.5),
        )

        # Bottom plot: Objective function approximation
        # For product-level, we approximate objective as function of total shipment
        # This is simplified - actual objective depends on individual allocations
        obj_values = []
        for total_x in x_range:
            # Approximate: objective increases with total shipment (shipment regularization)
            # and with constraint violations
            obj_val = self.settings.weight_shipment * total_x
            
            # Add penalty for factory supply violation
            if total_x > factory_supply:
                obj_val += 1000 * (total_x - factory_supply)  # Large penalty
            
            # Add penalty for target violation
            coverage = total_x + total_inventory
            if coverage < target_coverage:
                obj_val += self.settings.weight_target_units * (target_coverage - coverage)
            
            obj_values.append(obj_val)

        obj_values = np.array(obj_values)
        ax2.plot(
            x_range,
            obj_values,
            "g-",
            linewidth=2,
            label="Objective Function (approximate)",
            alpha=0.8,
        )

        # Mark optimal point
        optimal_obj = self.solution.objective_value if self.solution.objective_value else 0.0
        ax2.plot(
            total_optimal_shipment,
            optimal_obj,
            "o",
            markersize=12,
            color="purple",
            label=f"Optimal: ({total_optimal_shipment:.2f}, {optimal_obj:.2f})",
            zorder=5,
        )

        ax2.axvline(
            x=total_optimal_shipment,
            color="purple",
            linestyle="--",
            linewidth=1.5,
            alpha=0.5,
        )

        ax2.set_xlabel("Total Shipment Quantity", fontsize=12, fontweight="bold")
        ax2.set_ylabel("Objective Value", fontsize=12)
        ax2.set_title(
            f"Objective Function: {self.product_id}",
            fontsize=14,
            fontweight="bold",
        )
        ax2.legend(loc="upper right", fontsize=9)
        ax2.grid(True, alpha=0.3)
        ax2.set_xlim(0, x_max)

        # Add parameter info
        param_text = (
            f"Product-Level Parameters:\n"
            f"Factory Supply: {factory_supply:.1f}\n"
            f"Target Units: {target_units:.1f}\n"
            f"Remaining Target: {remaining_target:.1f}\n"
            f"Target Coverage Ratio: {self.settings.target_coverage_ratio}\n"
            f"Total Inventory: {total_inventory:.1f}\n"
            f"Total Shipment: {total_optimal_shipment:.1f}\n"
            f"Total Coverage: {optimal_total_coverage:.1f}"
        )
        ax2.text(
            0.98,
            0.98,
            param_text,
            transform=ax2.transAxes,
            fontsize=9,
            verticalalignment="top",
            horizontalalignment="right",
            bbox=dict(boxstyle="round", facecolor="lightblue", alpha=0.5),
        )

        plt.tight_layout()

        if output_path:
            plt.savefig(output_path, dpi=300, bbox_inches="tight")
            print_success(f"Plot saved to: {output_path}")
        else:
            plt.show()

        plt.close()


def resolve_product_id(product_identifier: str, data: Any) -> Optional[str]:
    """
    Resolve a product identifier (ID or English name) to a product ID.
    
    Args:
        product_identifier: Either a product ID or an English product name
        data: OptimizationData instance with product_names_en mapping
        
    Returns:
        Product ID if found, None otherwise
    """
    # First check if it's a direct product ID match
    if product_identifier in data.products:
        return product_identifier
    
    # If not, try to find by English name (reverse lookup)
    if hasattr(data, 'product_names_en') and data.product_names_en:
        # Create reverse mapping: English name -> product ID
        # Handle potential duplicates by taking the first match
        name_to_id = {}
        for pid, name in data.product_names_en.items():
            if name and name not in name_to_id:  # Only add first occurrence
                name_to_id[name] = pid
        
        if product_identifier in name_to_id:
            return name_to_id[product_identifier]
    
    return None


def get_product_display_name(product_id: str, data: Any) -> str:
    """Get English display name for a product ID, or return the ID if name not available."""
    if hasattr(data, 'product_names_en') and data.product_names_en:
        return data.product_names_en.get(product_id, product_id)
    return product_id


def visualize_product_level(
    product_identifier: str,
    snapshot_date: date,
    database_type: str = "test",
    settings: Optional[OptimizationSettings] = None,
    output_dir: Optional[Path] = None,
) -> None:
    """Visualize optimization at product level showing all distributors."""
    print_action(f"Loading data for product '{product_identifier}'...")

    # Initialize database
    factory = DBConnectionFactory()
    sql_executor = SQLExecutor(factory)

    # Load data
    loader = SnapshotDataLoader(sql_executor=sql_executor, database_type=database_type)
    if settings is None:
        settings = get_default_settings()

    data = loader.load_optimization_data(
        snapshot_date=snapshot_date,
        snapshot_month=None,
        settings=settings,
    )

    # Resolve product identifier (ID or English name) to product ID
    product_id = resolve_product_id(product_identifier, data)
    if product_id is None:
        print_error(f"Product '{product_identifier}' not found in data")
        # Show available products with their English names
        available_products = []
        for pid in sorted(data.products):
            display_name = get_product_display_name(pid, data)
            if display_name != pid:
                available_products.append(f"{display_name} (ID: {pid})")
            else:
                available_products.append(pid)
        print_info(f"Available products: {', '.join(available_products)}")
        return
    
    # Show which product was resolved
    display_name = get_product_display_name(product_id, data)
    if display_name != product_identifier:
        print_info(f"Resolved '{product_identifier}' to product ID: {product_id} ({display_name})")

    # Build and solve model
    print_action("Building and solving optimization model...")
    constraints = [
        FactorySupplyConstraint(),
        DeliveryHistoryConstraint(),
        DeliverySmoothingConstraint(),
        DemandCoverageConstraint(),
        ProductTargetUnitsConstraint(),
        ShipmentMinimizationConstraint(),
    ]

    builder = ModelBuilder(constraints)
    result = builder.build(data, settings_override=settings)

    from src.optimization.solvers import solve

    solution = solve(
        result.model,
        result.decision_variables,
        method="CBC",
        data=data,
    )

    if not solution.is_optimal:
        print_error(f"Solution is not optimal: {solution.status}")
        return

    # Create visualizer (no distributor specified)
    visualizer = EnhancedOptimizationVisualizer(
        None, product_id, data, result, solution, settings
    )

    # Create plot
    if output_dir:
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = (
            output_dir
            / f"product_level_{product_id}_{snapshot_date.strftime('%Y%m%d')}.png"
        )
    else:
        output_path = None

    print_action("Creating product-level visualization...")
    visualizer.create_product_level_plot(output_path)


def visualize_single_run(
    distributor_id: str,
    product_identifier: str,
    snapshot_date: date,
    database_type: str = "test",
    settings: Optional[OptimizationSettings] = None,
    output_dir: Optional[Path] = None,
) -> None:
    """Run optimization and create visualization."""
    print_action(f"Loading data for {distributor_id} × '{product_identifier}'...")

    # Initialize database
    factory = DBConnectionFactory()
    sql_executor = SQLExecutor(factory)

    # Load data
    loader = SnapshotDataLoader(sql_executor=sql_executor, database_type=database_type)
    if settings is None:
        settings = get_default_settings()

    data = loader.load_optimization_data(
        snapshot_date=snapshot_date,
        snapshot_month=None,
        settings=settings,
    )

    # Verify distributor exists
    if distributor_id not in data.distributors:
        print_error(f"Distributor '{distributor_id}' not found in data")
        print_info(f"Available distributors: {', '.join(data.distributors)}")
        return

    # Resolve product identifier (ID or English name) to product ID
    product_id = resolve_product_id(product_identifier, data)
    if product_id is None:
        print_error(f"Product '{product_identifier}' not found in data")
        # Show available products with their English names
        available_products = []
        for pid in sorted(data.products):
            display_name = get_product_display_name(pid, data)
            if display_name != pid:
                available_products.append(f"{display_name} (ID: {pid})")
            else:
                available_products.append(pid)
        print_info(f"Available products: {', '.join(available_products)}")
        return
    
    # Show which product was resolved
    display_name = get_product_display_name(product_id, data)
    if display_name != product_identifier:
        print_info(f"Resolved '{product_identifier}' to product ID: {product_id} ({display_name})")

    # Build and solve model
    print_action("Building and solving optimization model...")
    constraints = [
        FactorySupplyConstraint(),
        DeliveryHistoryConstraint(),
        DeliverySmoothingConstraint(),
        DemandCoverageConstraint(),
        ProductTargetUnitsConstraint(),
        ShipmentMinimizationConstraint(),
    ]

    builder = ModelBuilder(constraints)
    result = builder.build(data, settings_override=settings)

    from src.optimization.solvers import solve

    solution = solve(
        result.model,
        result.decision_variables,
        method="CBC",
        data=data,
    )

    if not solution.is_optimal:
        print_error(f"Solution is not optimal: {solution.status}")
        return

    # Create visualizer
    visualizer = EnhancedOptimizationVisualizer(
        distributor_id, product_id, data, result, solution, settings
    )

    # Create plot
    if output_dir:
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = (
            output_dir
            / f"optimization_{distributor_id}_{product_id}_{snapshot_date.strftime('%Y%m%d')}.png"
        )
    else:
        output_path = None

    print_action("Creating visualization...")
    visualizer.create_constraint_and_objective_plot(output_path)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Visualize optimization with constraint and objective line charts"
    )
    parser.add_argument(
        "--distributor",
        type=str,
        help="Distributor ID. If omitted, shows product-level view.",
    )
    parser.add_argument(
        "--product",
        type=str,
        required=True,
        help="Product ID or English product name to visualize",
    )
    parser.add_argument(
        "--date",
        type=str,
        required=True,
        help="Snapshot date (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--database",
        type=str,
        default="test",
        choices=["test", "source"],
        help="Database type (default: test)",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        help="Directory to save plots",
    )
    parser.add_argument(
        "--preset",
        type=str,
        help="Use a specific constraint preset",
    )

    args = parser.parse_args()

    try:
        snapshot_date = date.fromisoformat(args.date)
    except ValueError:
        print_error(f"Invalid date format: {args.date}. Use YYYY-MM-DD")
        return

    output_dir = Path(args.output_dir) if args.output_dir else None

    settings = None
    if args.preset:
        settings = get_constraint_preset(args.preset)
        if settings is None:
            print_error(f"Preset '{args.preset}' not found")
            return
        print_info(f"Using preset: {args.preset}")

    if args.distributor:
        visualize_single_run(
            args.distributor,
            args.product,
            snapshot_date,
            database_type=args.database,
            settings=settings,
            output_dir=output_dir,
        )
    else:
        visualize_product_level(
            args.product,
            snapshot_date,
            database_type=args.database,
            settings=settings,
            output_dir=output_dir,
        )


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nInterrupted by user.")
        sys.exit(0)
    except Exception as e:
        print_error(f"Error: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
