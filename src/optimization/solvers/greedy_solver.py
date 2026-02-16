"""Greedy heuristic solver -- proportional allocation by target coverage."""

from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

from src.optimization.lp import Model, Variable, evaluate_objective
from src.optimization.solvers.base import BaseSolver, Solution
from src.optimization.solvers._utils import greedy_allocate, set_slacks_for_feasibility


class GreedySolver(BaseSolver):
    """Fast baseline heuristic. Proportional allocation by target coverage shortfall.

    No external dependencies. Accepts ``data`` either in the constructor
    (backward-compatible) or via the ``solve()`` keyword argument (preferred).
    """

    name = "Greedy"
    category = "heuristic"

    def __init__(self, data: Any = None) -> None:
        self._data = data

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
            raise ValueError("GreedySolver requires OptimizationData (data=...)")

        variable_values = greedy_allocate(effective_data, decision_variables)
        set_slacks_for_feasibility(model, variable_values)
        for var in model.variables:
            if var not in variable_values:
                variable_values[var] = 0.0
        obj = evaluate_objective(model, variable_values)
        return Solution(
            status="Feasible",
            objective_value=obj,
            variable_values=variable_values,
            is_optimal=False,
            solver_name=self.name,
        )
