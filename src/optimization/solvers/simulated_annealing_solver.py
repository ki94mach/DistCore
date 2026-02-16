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
    """Core Simulated Annealing parameters.

    These are standard SA parameters that apply to any problem domain.
    See ``docs/optimization-fine-tuning.md`` for guidance on choosing values.
    """

    max_iter: int = 5000
    initial_temp: float = 1000.0
    min_temp: float = 0.01
    cooling_rate: float = 0.995  # Slower = more exploration; 0.95 cools fast, often stuck
    step_scale: float = 0.2

    @classmethod
    def from_dict(cls, d: Optional[Dict[str, Any]]) -> SAConfig:
        """Build config from a dict. Unknown keys are ignored. Uses dataclass defaults when key missing."""
        defaults = cls()
        if not d:
            return defaults
        return cls(
            max_iter=int(d.get("max_iter", defaults.max_iter)),
            initial_temp=float(d.get("initial_temp", defaults.initial_temp)),
            min_temp=float(d.get("min_temp", defaults.min_temp)),
            cooling_rate=float(d.get("cooling_rate", defaults.cooling_rate)),
            step_scale=float(d.get("step_scale", defaults.step_scale)),
        )


@dataclass
class ProblemSpecificConfig:
    """Problem-specific adaptations for Simulated Annealing.

    These parameters exploit domain knowledge about the distributor allocation problem:
    - Product-grouped structure (transfer moves)
    - Objective function bias toward lower shipment (decrease bias, initial scale)
    See ``docs/optimization-fine-tuning.md`` for guidance on choosing values.
    """

    transfer_fraction: float = 0.5  # Fraction of moves that are same-product transfers
    # Start from scaled-down greedy so SA can reach low-delivery regime (optimal often has much lower total delivery)
    initial_scale: float = 0.15  # 1.0 = pure greedy; 0.15 = 15% of greedy allocation per variable
    decrease_bias: float = 0.6  # For single-var moves, prob of trying a decrease (helps reduce total delivery)

    @classmethod
    def from_dict(cls, d: Optional[Dict[str, Any]]) -> ProblemSpecificConfig:
        """Build config from a dict. Unknown keys are ignored. Uses dataclass defaults when key missing."""
        defaults = cls()
        if not d:
            return defaults
        return cls(
            transfer_fraction=float(d.get("transfer_fraction", defaults.transfer_fraction)),
            initial_scale=float(d.get("initial_scale", defaults.initial_scale)),
            decrease_bias=float(d.get("decrease_bias", defaults.decrease_bias)),
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
        problem_config: Optional[ProblemSpecificConfig] = None,
        problem_config_dict: Optional[Dict[str, Any]] = None,
    ) -> None:
        self._data = data
        if config_dict is not None:
            # Backward compatibility: parse combined dict into both configs
            self._sa_config = SAConfig.from_dict(config_dict)
            self._problem_config = ProblemSpecificConfig.from_dict(config_dict)
        else:
            self._sa_config = config or SAConfig()
            if problem_config_dict is not None:
                self._problem_config = ProblemSpecificConfig.from_dict(problem_config_dict)
            else:
                self._problem_config = problem_config or ProblemSpecificConfig()

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

        # Parse options dict into both configs (backward compatible: single dict can contain all params)
        if options:
            sa_cfg = SAConfig.from_dict(options)
            problem_cfg = ProblemSpecificConfig.from_dict(options)
        else:
            sa_cfg = self._sa_config
            problem_cfg = self._problem_config

        # Start from (scaled) greedy solution so we can reach low-delivery regime (optimal often has much lower total)
        variable_values = greedy_allocate(effective_data, decision_variables)
        if problem_cfg.initial_scale != 1.0:
            for (_, _), var in decision_variables.items():
                variable_values[var] *= problem_cfg.initial_scale
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

        # Group by product for transfer moves (same-product reallocation keeps supply feasible)
        product_to_vars: Dict[str, List[Variable]] = {}
        for (_d, product), var in decision_variables.items():
            product_to_vars.setdefault(product, []).append(var)
        products_with_pairs: List[str] = [p for p, vlist in product_to_vars.items() if len(vlist) >= 2]

        temp = sa_cfg.initial_temp
        best_values = dict(variable_values)
        best_obj = evaluate_objective(model, best_values)
        current_values = dict(variable_values)
        current_obj = best_obj

        for _ in range(sa_cfg.max_iter):
            if temp < sa_cfg.min_temp:
                break

            use_transfer = (
                products_with_pairs
                and random.random() < problem_cfg.transfer_fraction
            )
            if use_transfer:
                # Transfer between two variables for the same product (keeps sum constant, so supply stays feasible)
                product = random.choice(products_with_pairs)
                v1, v2 = random.sample(product_to_vars[product], 2)
                low1, up1 = v1.low, v1.up if v1.up is not None else 1e9
                low2, up2 = v2.low, v2.up if v2.up is not None else 1e9
                a, b = current_values[v1], current_values[v2]
                # v1' = a - delta, v2' = b + delta; keep both in [low, up]
                delta_lo = max(a - up1, low2 - b)
                delta_hi = min(a - low1, up2 - b)
                if delta_lo > delta_hi:
                    temp *= sa_cfg.cooling_rate
                    continue
                max_step = sa_cfg.step_scale * min(up1 - low1, up2 - low2)
                delta = max(delta_lo, min(delta_hi, max_step * (2 * random.random() - 1)))
                current_values[v1] = a - delta
                current_values[v2] = b + delta
            else:
                # Single-variable perturbation (decrease bias helps reduce total delivery toward optimal)
                var = random.choice(decision_vars_list)
                low = var.low
                up = var.up if var.up is not None else 1e9
                step = (up - low) * sa_cfg.step_scale * (2 * random.random() - 1)
                if problem_cfg.decrease_bias > 0 and random.random() < problem_cfg.decrease_bias:
                    step = -abs(step)  # Prefer decrease to explore low-delivery region
                new_val = max(low, min(up, current_values[var] + step))
                old_val = current_values[var]
                current_values[var] = new_val
                set_slacks_for_feasibility(model, current_values)
                if not is_feasible(model, current_values):
                    current_values[var] = old_val
                    set_slacks_for_feasibility(model, current_values)
                    temp *= sa_cfg.cooling_rate
                    continue

            set_slacks_for_feasibility(model, current_values)
            if not is_feasible(model, current_values):
                if use_transfer:
                    current_values[v1] = a
                    current_values[v2] = b
                    set_slacks_for_feasibility(model, current_values)
                temp *= sa_cfg.cooling_rate
                continue
            new_obj = evaluate_objective(model, current_values)
            delta_obj = new_obj - current_obj
            if delta_obj <= 0 or random.random() < math.exp(-delta_obj / temp):
                current_obj = new_obj
                if current_obj < best_obj:
                    best_obj = current_obj
                    best_values = dict(current_values)
            else:
                if use_transfer:
                    current_values[v1] = a
                    current_values[v2] = b
                else:
                    current_values[var] = old_val
                set_slacks_for_feasibility(model, current_values)
            temp *= sa_cfg.cooling_rate

        return Solution(
            status="Feasible",
            objective_value=best_obj,
            variable_values=best_values,
            is_optimal=False,
            solver_name=self.name,
        )
