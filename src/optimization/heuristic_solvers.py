"""Heuristic and metaheuristic solvers for the optimization layer.

These solvers do not require an external LP solver. They produce feasible solutions
suitable for comparison and fallback. Priority order for evaluation:

1. Greedy   - Baseline, no dependencies, very fast.
2. SA       - Simulated annealing; better quality, still no heavy deps.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from src.optimization.data import OptimizationData
from src.optimization.solver import Solution
from src.optimization.lp import (
    Model,
    Variable,
    evaluate_objective,
    is_feasible,
)


def _set_slacks_for_feasibility(
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


def _greedy_allocate(
    data: OptimizationData,
    decision_variables: Dict[Tuple[str, str], Variable],
) -> Dict[Variable, float]:
    """Proportional allocation by coverage demand, respecting factory supply and delivery history."""
    variable_values: Dict[Variable, float] = {}
    for var in decision_variables.values():
        variable_values[var] = 0.0

    for product in data.products:
        supply = data.factory_supply(product)
        if supply <= 0:
            continue
        eligible = [
            (d, product)
            for d in data.distributors
            if data.has_recent_delivery(d, product)
        ]
        total_demand = sum(data.coverage_demand(d, p) for d, p in eligible)
        if total_demand <= 0:
            continue
        for distributor, p in eligible:
            demand = data.coverage_demand(distributor, p)
            x_var = decision_variables[(distributor, p)]
            variable_values[x_var] = supply * (demand / total_demand)
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


class GreedySolver:
    """Priority 1: Fast baseline solver. No dependencies. Proportional allocation by demand."""

    def __init__(self, data: OptimizationData) -> None:
        self.data = data
        self.solver_name = "Greedy"

    def solve(
        self,
        model: Model,
        decision_variables: Dict[Tuple[str, str], Variable],
    ) -> Solution:

        variable_values = _greedy_allocate(self.data, decision_variables)
        # Do not pre-fill slacks: _set_slacks_for_feasibility must see them as "not in variable_values"
        # so it can set them; otherwise slacks stay 0 and the objective is wrong.
        _set_slacks_for_feasibility(model, variable_values)
        # Ensure any remaining model variables (e.g. unused) have a value for the returned dict
        for var in model.variables:
            if var not in variable_values:
                variable_values[var] = 0.0
        obj = evaluate_objective(model, variable_values)
        return Solution(
            status="Feasible",
            objective_value=obj,
            variable_values=variable_values,
            is_optimal=False,
            solver_name=self.solver_name,
        )


@dataclass
class _SAConfig:
    max_iter: int = 5000
    initial_temp: float = 1000.0
    min_temp: float = 0.01
    cooling_rate: float = 0.995
    step_scale: float = 0.1

    @classmethod
    def from_dict(cls, d: Optional[Dict[str, Any]]) -> "_SAConfig":
        """Build config from a dict (e.g. solver_options['SimulatedAnnealing']). Unknown keys ignored."""
        if not d:
            return cls()
        return cls(
            max_iter=int(d.get("max_iter", 5000)),
            initial_temp=float(d.get("initial_temp", 1000.0)),
            min_temp=float(d.get("min_temp", 0.01)),
            cooling_rate=float(d.get("cooling_rate", 0.995)),
            step_scale=float(d.get("step_scale", 0.1)),
        )


class SimulatedAnnealingSolver:
    """Priority 2: Metaheuristic solver. Improves on a starting solution by random perturbations."""

    def __init__(
        self,
        data: OptimizationData,
        config: Optional[_SAConfig] = None,
        config_dict: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.data = data
        if config_dict is not None:
            self.config = _SAConfig.from_dict(config_dict)
        else:
            self.config = config or _SAConfig()
        self.solver_name = "SimulatedAnnealing"

    def solve(
        self,
        model: Model,
        decision_variables: Dict[Tuple[str, str], Variable],
    ) -> Solution:

        # Start from greedy solution (do not pre-fill slacks so _set_slacks_for_feasibility sets them)
        variable_values = _greedy_allocate(self.data, decision_variables)
        _set_slacks_for_feasibility(model, variable_values)
        for var in model.variables:
            if var not in variable_values:
                variable_values[var] = 0.0

        # Only perturb decision variables (not slacks); slacks recomputed after each move
        decision_vars_list: List[Variable] = list(decision_variables.values())
        n = len(decision_vars_list)
        if n == 0:
            return Solution(
                status="Feasible",
                objective_value=evaluate_objective(model, variable_values),
                variable_values=variable_values,
                is_optimal=False,
                solver_name=self.solver_name,
            )

        cfg = self.config
        temp = cfg.initial_temp
        best_values = dict(variable_values)
        best_obj = evaluate_objective(model, best_values)
        current_values = dict(variable_values)
        current_obj = best_obj

        for _ in range(cfg.max_iter):
            if temp < cfg.min_temp:
                break
            # Pick a random decision variable and perturb
            var = random.choice(decision_vars_list)
            low = var.low
            up = var.up if var.up is not None else 1e9
            step = (up - low) * cfg.step_scale * (2 * random.random() - 1)
            new_val = max(low, min(up, current_values[var] + step))
            old_val = current_values[var]
            current_values[var] = new_val
            _set_slacks_for_feasibility(model, current_values)
            if not is_feasible(model, current_values):
                current_values[var] = old_val
                _set_slacks_for_feasibility(model, current_values)
                temp *= cfg.cooling_rate
                continue
            new_obj = evaluate_objective(model, current_values)
            delta = new_obj - current_obj
            if delta <= 0 or random.random() < math.exp(-delta / temp):
                current_obj = new_obj
                if current_obj < best_obj:
                    best_obj = current_obj
                    best_values = dict(current_values)
            else:
                current_values[var] = old_val
                _set_slacks_for_feasibility(model, current_values)
            temp *= cfg.cooling_rate

        return Solution(
            status="Feasible",
            objective_value=best_obj,
            variable_values=best_values,
            is_optimal=False,
            solver_name=self.solver_name,
        )
