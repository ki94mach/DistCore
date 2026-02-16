"""Shared utilities for heuristic and metaheuristic solvers."""

from __future__ import annotations

from typing import Dict, Optional, Tuple

from src.optimization.data import OptimizationData
from src.optimization.lp import Model, Variable


def set_slacks_for_feasibility(
    model: Model,
    variable_values: Dict[Variable, float],
) -> None:
    """Set slack variables to minimum non-negative values that satisfy constraints (in-place)."""
    for constraint in model.constraints:
        slack_var: Optional[Variable] = None
        slack_coeff = 0.0
        other_lhs = constraint.expression.constant
        for var, coeff in constraint.expression.coefficients.items():
            if var in variable_values:
                other_lhs += coeff * variable_values[var]
            else:
                slack_var = var
                slack_coeff = coeff
        if slack_var is None:
            continue
        need = constraint.rhs - other_lhs
        if constraint.sense == ">=":
            if slack_coeff > 0:
                slack_val = max(0.0, need / slack_coeff)
            else:
                slack_val = 0.0
        elif constraint.sense == "<=":
            if slack_coeff < 0:
                slack_val = max(0.0, need / slack_coeff)
            else:
                slack_val = 0.0
        else:
            slack_val = max(0.0, need / slack_coeff) if slack_coeff != 0 else 0.0
        variable_values[slack_var] = slack_val


def greedy_allocate(
    data: OptimizationData,
    decision_variables: Dict[Tuple[str, str], Variable],
) -> Dict[Variable, float]:
    """Proportional allocation by target coverage shortfall, respecting factory supply and delivery history."""
    variable_values: Dict[Variable, float] = {}
    for var in decision_variables.values():
        variable_values[var] = 0.0

    ratio = data.settings.coverage_ratio
    for product in data.products:
        supply = data.factory_supply(product)
        if supply <= 0:
            continue
        eligible = [
            (d, product)
            for d in data.distributors
            if data.has_recent_delivery(d, product)
        ]
        if not eligible:
            continue
        # Product-level target: total (inv + x) >= ratio * remaining_target_units
        target_total = ratio * data.remaining_target_units(product)
        total_inv = sum(data.inventory(d, product) for d in data.distributors)
        total_demand = sum(data.coverage_demand(d, p) for d, p in eligible)
        # Per-distributor target share (by demand proportion), then shortfall vs inventory
        for distributor, p in eligible:
            if total_demand > 0:
                target_share = target_total * (
                    data.coverage_demand(distributor, p) / total_demand
                )
            else:
                target_share = target_total / len(eligible)
            need = max(0.0, target_share - data.inventory(distributor, product))
            x_var = decision_variables[(distributor, p)]
            variable_values[x_var] = need  # store need for proportional split
        total_need = sum(
            variable_values[decision_variables[(d, product)]]
            for d in data.distributors
            if (d, product) in decision_variables
        )
        if total_need <= 0:
            # No shortfall: allocate by demand proportion, or equally if no demand
            if total_demand > 0:
                for distributor, p in eligible:
                    demand = data.coverage_demand(distributor, p)
                    x_var = decision_variables[(distributor, p)]
                    variable_values[x_var] = supply * (demand / total_demand)
            else:
                equal = supply / len(eligible)
                for distributor, p in eligible:
                    x_var = decision_variables[(distributor, p)]
                    variable_values[x_var] = equal
        else:
            # Allocate supply in proportion to target shortfall
            for distributor, p in eligible:
                need = variable_values[decision_variables[(distributor, p)]]
                x_var = decision_variables[(distributor, p)]
                variable_values[x_var] = supply * (need / total_need)
        # Cap total allocated to supply (float safety)
        total_allocated = sum(
            variable_values[decision_variables[(d, product)]]
            for d in data.distributors
            if (d, product) in decision_variables
        )
        if total_allocated > supply + 1e-6:
            scale = supply / total_allocated
            for d in data.distributors:
                if (d, product) in decision_variables:
                    v = decision_variables[(d, product)]
                    variable_values[v] *= scale

    return variable_values
