"""Simulated Annealing metaheuristic solver."""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from src.optimization.lp import Model, Variable, evaluate_objective, is_feasible
from src.optimization.solvers.base import BaseSolver, Solution
from src.optimization.solvers._utils import greedy_allocate, set_slacks_for_feasibility


@dataclass
class SAConfig:
    """Tuning parameters for the Simulated Annealing solver.

    See ``docs/optimization-fine-tuning.md`` for guidance on choosing values.
    """

    max_iter: int = 5000
    initial_temp: float = 1000.0
    min_temp: float = 0.01
    cooling_rate: float = 0.995
    step_scale: float = 0.1

    @classmethod
    def from_dict(cls, d: Optional[Dict[str, Any]]) -> SAConfig:
        """Build config from a dict. Unknown keys are ignored."""
        if not d:
            return cls()
        return cls(
            max_iter=int(d.get("max_iter", 5000)),
            initial_temp=float(d.get("initial_temp", 1000.0)),
            min_temp=float(d.get("min_temp", 0.01)),
            cooling_rate=float(d.get("cooling_rate", 0.995)),
            step_scale=float(d.get("step_scale", 0.1)),
        )


class SimulatedAnnealingSolver(BaseSolver):
    """Metaheuristic solver. Improves on a greedy starting solution via random perturbations.

    No external dependencies. Accepts ``data`` either in the constructor
    (backward-compatible) or via the ``solve()`` keyword argument (preferred).
    """

    name = "SimulatedAnnealing"
    category = "metaheuristic"

    def __init__(
        self,
        data: Any = None,
        config: Optional[SAConfig] = None,
        config_dict: Optional[Dict[str, Any]] = None,
    ) -> None:
        self._data = data
        if config_dict is not None:
            self._config = SAConfig.from_dict(config_dict)
        else:
            self._config = config or SAConfig()

    @classmethod
    def is_available(cls) -> bool:
        return True

    def solve(
        self,
        model: Model,
        decision_variables: Dict[Tuple[str, str], Variable],
        *,
        data: Any = None,
        options: Optional[Dict[str, Any]] = None,
    ) -> Solution:
        effective_data = data if data is not None else self._data
        if effective_data is None:
            raise ValueError(
                "SimulatedAnnealingSolver requires OptimizationData (data=...)"
            )

        cfg = SAConfig.from_dict(options) if options else self._config

        # Start from greedy solution
        variable_values = greedy_allocate(effective_data, decision_variables)
        set_slacks_for_feasibility(model, variable_values)
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
                solver_name=self.name,
            )

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
            set_slacks_for_feasibility(model, current_values)
            if not is_feasible(model, current_values):
                current_values[var] = old_val
                set_slacks_for_feasibility(model, current_values)
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
                set_slacks_for_feasibility(model, current_values)
            temp *= cfg.cooling_rate

        return Solution(
            status="Feasible",
            objective_value=best_obj,
            variable_values=best_values,
            is_optimal=False,
            solver_name=self.name,
        )
