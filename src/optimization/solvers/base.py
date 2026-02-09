"""Solver base class and result types for the optimization layer.

This mirrors the constraint pattern in ``constraints/base.py``: every solver
subclass declares metadata (``name``, ``category``) and implements ``solve()``
and ``is_available()``.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

from src.optimization.lp import Model, Variable


@dataclass
class Solution:
    """Solution result from a solver."""

    status: str
    objective_value: Optional[float]
    variable_values: Dict[Variable, float]
    is_optimal: bool
    solver_name: str

    @property
    def is_feasible(self) -> bool:
        """Check if solution is feasible."""
        return self.status in {"Optimal", "Feasible"}


class BaseSolver(ABC):
    """Abstract base class for all optimization solvers.

    Category values:
        - ``"exact"``         – LP/MIP solvers that guarantee optimality (CBC, GLPK, Scipy).
        - ``"heuristic"``     – Fast constructive heuristics (Greedy).
        - ``"metaheuristic"`` – Iterative improvement methods (SA, GA, ...).
    """

    name: str = ""
    category: str = ""  # "exact" | "heuristic" | "metaheuristic"

    @abstractmethod
    def solve(
        self,
        model: Model,
        decision_variables: Dict[Tuple[str, str], Variable],
        *,
        data: Any = None,
        options: Optional[Dict[str, Any]] = None,
    ) -> Solution:
        """Solve the model and return a Solution.

        Args:
            model: The abstract LP model.
            decision_variables: Mapping ``(distributor, product) -> Variable``.
            data: ``OptimizationData``; required for heuristic/metaheuristic solvers.
            options: Solver-specific tuning parameters.
        """
        ...

    @classmethod
    @abstractmethod
    def is_available(cls) -> bool:
        """Return True if this solver's runtime dependencies are installed."""
        ...
