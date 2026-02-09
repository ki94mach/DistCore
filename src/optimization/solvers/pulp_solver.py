"""PuLP-based exact LP solvers (CBC, GLPK).

PuLP is imported lazily so the module can be loaded even when PuLP is not
installed (``is_available()`` will simply return ``False``).
"""

from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

from src.optimization.lp import Model, Variable
from src.optimization.solvers.base import BaseSolver, Solution


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _pulp_available(cmd_name: str) -> bool:
    """Check if a PuLP solver backend is installed and reachable."""
    try:
        import pulp
        solver_class = getattr(pulp, cmd_name, None)
        if solver_class is None:
            return False
        return solver_class().available()
    except Exception:
        return False


def _solve_with_pulp(model: Model, cmd_name: str, solver_name: str) -> Solution:
    """Core PuLP solve logic shared by all PuLP-backed solvers."""
    import pulp

    sense = pulp.LpMinimize
    if model.objective and model.objective.sense == "max":
        sense = pulp.LpMaximize

    prob = pulp.LpProblem("DistributionOptimization", sense)

    # Create variable mapping: abstract Variable -> PuLP variable
    pulp_vars: Dict[Variable, Any] = {}
    for var in model.variables:
        pulp_vars[var] = pulp.LpVariable(
            name=var.name,
            lowBound=var.low,
            upBound=var.up,
            cat=pulp.LpContinuous,
        )

    # Add constraints
    for constraint in model.constraints:
        lhs = pulp.LpAffineExpression()
        for var, coeff in constraint.expression.coefficients.items():
            if var in pulp_vars:
                lhs += coeff * pulp_vars[var]
        lhs += constraint.expression.constant
        if constraint.sense == "<=":
            prob += lhs <= constraint.rhs, constraint.name
        elif constraint.sense == ">=":
            prob += lhs >= constraint.rhs, constraint.name
        elif constraint.sense == "=":
            prob += lhs == constraint.rhs, constraint.name

    # Add objective
    if model.objective:
        obj = pulp.LpAffineExpression()
        for var, coeff in model.objective.expression.coefficients.items():
            if var in pulp_vars:
                obj += coeff * pulp_vars[var]
        obj += model.objective.expression.constant
        prob += obj

    # Solve
    try:
        pulp_solver = getattr(pulp, cmd_name)(msg=0)
        status_code = prob.solve(pulp_solver)
        status = pulp.LpStatus[status_code]

        variable_values: Dict[Variable, float] = {}
        for var in model.variables:
            if var in pulp_vars:
                value = pulp_vars[var].varValue
                variable_values[var] = value if value is not None else 0.0

        objective_value = pulp.value(prob.objective) if model.objective else None

        return Solution(
            status=status,
            objective_value=objective_value,
            variable_values=variable_values,
            is_optimal=(status == "Optimal"),
            solver_name=solver_name,
        )
    except Exception as e:
        raise RuntimeError(f"Solver failed: {str(e)}") from e


# ---------------------------------------------------------------------------
# Registered solvers
# ---------------------------------------------------------------------------

class CBCSolver(BaseSolver):
    """Exact LP via PuLP + CBC (Coin-or Branch and Cut). Recommended."""

    name = "CBC"
    category = "exact"

    @classmethod
    def is_available(cls) -> bool:
        return _pulp_available("PULP_CBC_CMD")

    def solve(
        self,
        model: Model,
        decision_variables: Dict[Tuple[str, str], Variable],
        *,
        data: Any = None,
        options: Optional[Dict[str, Any]] = None,
    ) -> Solution:
        return _solve_with_pulp(model, "PULP_CBC_CMD", self.name)


class GLPKSolver(BaseSolver):
    """Exact LP via PuLP + GLPK (GNU Linear Programming Kit)."""

    name = "GLPK"
    category = "exact"

    @classmethod
    def is_available(cls) -> bool:
        return _pulp_available("GLPK_CMD")

    def solve(
        self,
        model: Model,
        decision_variables: Dict[Tuple[str, str], Variable],
        *,
        data: Any = None,
        options: Optional[Dict[str, Any]] = None,
    ) -> Solution:
        return _solve_with_pulp(model, "GLPK_CMD", self.name)


# ---------------------------------------------------------------------------
# Backward-compatible convenience wrapper
# ---------------------------------------------------------------------------

class PuLPSolver(BaseSolver):
    """Convenience class that accepts a ``solver_name`` parameter.

    Prefer ``CBCSolver`` or ``GLPKSolver`` directly for new code.
    """

    category = "exact"
    _CMD_MAP = {
        "CBC": "PULP_CBC_CMD",
        "GLPK": "GLPK_CMD",
        "PULP_CBC_CMD": "PULP_CBC_CMD",
    }

    def __init__(self, solver_name: str = "CBC"):
        self.solver_name = solver_name
        self.name = solver_name
        self._pulp_cmd = self._CMD_MAP.get(solver_name.upper(), "PULP_CBC_CMD")

    @classmethod
    def is_available(cls) -> bool:
        # Default check for CBC
        return _pulp_available("PULP_CBC_CMD")

    def solve(
        self,
        model: Model,
        decision_variables: Dict[Tuple[str, str], Variable],
        *,
        data: Any = None,
        options: Optional[Dict[str, Any]] = None,
    ) -> Solution:
        return _solve_with_pulp(model, self._pulp_cmd, self.name)
