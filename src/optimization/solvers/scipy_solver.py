"""Exact LP solver via scipy.optimize.linprog (HiGHS backend).

Scipy is imported lazily so the module can be loaded even when scipy is not
installed (``is_available()`` will simply return ``False``).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from src.optimization.lp import Model, Variable
from src.optimization.solvers.base import BaseSolver, Solution


def _scipy_available() -> bool:
    """Check if scipy is installed."""
    try:
        from scipy.optimize import linprog  # noqa: F401
        return True
    except ImportError:
        return False


class ScipySolver(BaseSolver):
    """Exact LP via scipy.optimize.linprog (HiGHS). No PuLP required."""

    name = "Scipy"
    category = "exact"

    @classmethod
    def is_available(cls) -> bool:
        return _scipy_available()

    def solve(
        self,
        model: Model,
        decision_variables: Dict[Tuple[str, str], Variable],
        *,
        data: Any = None,
        options: Optional[Dict[str, Any]] = None,
    ) -> Solution:
        from scipy.optimize import linprog
        import numpy as np

        n = len(model.variables)
        var_to_idx = {v: i for i, v in enumerate(model.variables)}

        # Objective: c @ x (minimize)
        c = np.zeros(n)
        if model.objective:
            for var, coeff in model.objective.expression.coefficients.items():
                if var in var_to_idx:
                    c[var_to_idx[var]] = coeff
            if model.objective.sense == "max":
                c = -c

        # Bounds
        bounds: List[Tuple[float, Optional[float]]] = []
        for var in model.variables:
            up = var.up if var.up is not None else None
            bounds.append((var.low, up))

        # Constraints: A_ub @ x <= b_ub, A_eq @ x = b_eq
        A_ub_list: List[List[float]] = []
        b_ub_list: List[float] = []
        A_eq_list: List[List[float]] = []
        b_eq_list: List[float] = []

        for constraint in model.constraints:
            row = [0.0] * n
            for var, coeff in constraint.expression.coefficients.items():
                if var in var_to_idx:
                    row[var_to_idx[var]] = coeff
            rhs = constraint.rhs - constraint.expression.constant
            if constraint.sense == "<=":
                A_ub_list.append(row)
                b_ub_list.append(rhs)
            elif constraint.sense == ">=":
                A_ub_list.append([-x for x in row])
                b_ub_list.append(-rhs)
            else:
                A_eq_list.append(row)
                b_eq_list.append(rhs)

        A_ub = np.array(A_ub_list) if A_ub_list else None
        b_ub = np.array(b_ub_list) if b_ub_list else None
        A_eq = np.array(A_eq_list) if A_eq_list else None
        b_eq = np.array(b_eq_list) if b_eq_list else None

        try:
            res = linprog(
                c, A_ub=A_ub, b_ub=b_ub, A_eq=A_eq, b_eq=b_eq,
                bounds=bounds, method="highs", options={"disp": False},
            )
        except ValueError:
            res = linprog(
                c, A_ub=A_ub, b_ub=b_ub, A_eq=A_eq, b_eq=b_eq,
                bounds=bounds, method="revised_simplex", options={"disp": False},
            )

        if not res.success:
            status = (
                "Infeasible" if res.status == 2
                else "Unbounded" if res.status == 3
                else "Failed"
            )
            variable_values = {var: 0.0 for var in model.variables}
            return Solution(
                status=status,
                objective_value=float(res.fun) if res.fun is not None else None,
                variable_values=variable_values,
                is_optimal=False,
                solver_name=self.name,
            )

        variable_values: Dict[Variable, float] = {}
        for i, var in enumerate(model.variables):
            val = res.x[i] if res.x is not None else 0.0
            variable_values[var] = float(val) if val is not None else 0.0

        return Solution(
            status="Optimal",
            objective_value=float(res.fun) if res.fun is not None else None,
            variable_values=variable_values,
            is_optimal=True,
            solver_name=self.name,
        )


# Backward-compatible alias
ScipyLinprogSolver = ScipySolver
