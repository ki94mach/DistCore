"""Solver integration for the optimization layer.

This module provides adapters to convert the abstract LP model to solver-specific
formats and solve optimization problems.

Solver priority for evaluation (best first for your use case):
  1. CBC / GLPK  - Exact LP (PuLP); use for reference quality.
  2. Scipy       - Exact LP (HiGHS); no extra binary, good fallback.
  3. Greedy      - Heuristic baseline; no deps, very fast.
  4. SimulatedAnnealing - Metaheuristic; better quality than greedy.

Installation: pip install pulp   (for CBC/GLPK)
              pip install scipy  (for Scipy; often already installed)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import pulp
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


class PuLPSolver:
    """Solver adapter for PuLP (Python Linear Programming)."""

    def __init__(self, solver_name: str = "CBC"):
        """
        Initialize the PuLP solver adapter.

        Args:
            solver_name: Name of the PuLP solver to use. Options:
                - "CBC" (default) - Coin-or Branch and Cut, open source
                - "GLPK" - GNU Linear Programming Kit, open source
        """
        self.solver_name = solver_name
        self._pulp_solver = self._get_pulp_solver(solver_name)

    def solve(self, model: Model, decision_variables: Dict[Tuple[str, str], Variable]) -> Solution:
        """
        Solve the optimization model using PuLP.

        Args:
            model: The abstract LP model to solve
            decision_variables: Dictionary mapping (distributor, product) to Variable

        Returns:
            Solution object with status, objective value, and variable values

        Raises:
            ValueError: If model is invalid
            RuntimeError: If solver fails
        """
        # Create PuLP problem
        prob = pulp.LpProblem("DistributionOptimization", self._get_objective_sense(model))

        # Create variable mapping: abstract Variable -> PuLP variable
        pulp_vars: Dict[Variable, pulp.LpVariable] = {}

        # Add variables
        for var in model.variables:
            pulp_var = pulp.LpVariable(
                name=var.name,
                lowBound=var.low,
                upBound=var.up,
                cat=pulp.LpContinuous,
            )
            pulp_vars[var] = pulp_var

        # Add constraints
        for constraint in model.constraints:
            # Build left-hand side expression
            lhs = pulp.LpAffineExpression()
            for var, coeff in constraint.expression.coefficients.items():
                if var in pulp_vars:
                    lhs += coeff * pulp_vars[var]
            lhs += constraint.expression.constant

            # Add constraint based on sense
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
            status_code = prob.solve(self._pulp_solver)
            status = pulp.LpStatus[status_code]

            # Extract solution
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
                solver_name=self.solver_name,
            )

        except Exception as e:
            raise RuntimeError(f"Solver failed: {str(e)}") from e

    def _get_objective_sense(self, model: Model) -> int:
        """Convert objective sense to PuLP constant."""
        if model.objective is None:
            return pulp.LpMinimize
        return pulp.LpMinimize if model.objective.sense == "min" else pulp.LpMaximize

    def _get_pulp_solver(self, solver_name: str):
        """
        Get the PuLP solver instance.

        Args:
            solver_name: Name of the solver

        Returns:
            PuLP solver instance (defaults to CBC)
        """

        solver_map = {
            "CBC": pulp.PULP_CBC_CMD(msg=0),  # Quiet mode
            "GLPK": pulp.GLPK_CMD(msg=0),
            "PULP_CBC_CMD": pulp.PULP_CBC_CMD(msg=0),
        }

        solver = solver_map.get(solver_name.upper())
        if solver is None:
            # Default to CBC
            return pulp.PULP_CBC_CMD(msg=0)
        return solver


# PuLP internal names for availability checks
_PULP_SOLVER_NAMES = {
    "CBC": "PULP_CBC_CMD",
    "GLPK": "GLPK_CMD",
}

# Priority order for evaluation: exact LP first, then heuristic/metaheuristic
SOLVER_PRIORITY: List[str] = [
    "CBC",
    "GLPK",
    "Scipy",
    "Greedy",
    "SimulatedAnnealing",
]


def _scipy_available() -> bool:
    try:
        from scipy.optimize import linprog
        return True
    except ImportError:
        return False


class ScipyLinprogSolver:
    """Priority 3: Exact LP via scipy.optimize.linprog (HiGHS). No PuLP required."""

    def __init__(self) -> None:
        self.solver_name = "Scipy"

    def solve(
        self, model: Model, decision_variables: Dict[Tuple[str, str], Variable]
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
        # Constant term ignored for optimum

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
                c,
                A_ub=A_ub,
                b_ub=b_ub,
                A_eq=A_eq,
                b_eq=b_eq,
                bounds=bounds,
                method="highs",
                options={"disp": False},
            )
        except ValueError:
            res = linprog(
                c,
                A_ub=A_ub,
                b_ub=b_ub,
                A_eq=A_eq,
                b_eq=b_eq,
                bounds=bounds,
                method="revised_simplex",
                options={"disp": False},
            )

        if not res.success:
            status = "Infeasible" if res.status == 2 else "Unbounded" if res.status == 3 else "Failed"
            variable_values = {var: 0.0 for var in model.variables}
            return Solution(
                status=status,
                objective_value=float(res.fun) if res.fun is not None else None,
                variable_values=variable_values,
                is_optimal=False,
                solver_name=self.solver_name,
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
            solver_name=self.solver_name,
        )


def is_solver_available(solver_name: str) -> bool:
    """
    Check if a solver is available on this system.

    Args:
        solver_name: One of "CBC", "GLPK", "Scipy", "Greedy", "SimulatedAnnealing"

    Returns:
        True if the solver can be used, False otherwise.
    """
    name = solver_name.strip()
    if name in ("Greedy", "SimulatedAnnealing"):
        return True
    if name == "Scipy":
        return _scipy_available()
    pulp_name = _PULP_SOLVER_NAMES.get(name.upper())
    if not pulp_name:
        return False
    try:
        solver_class = getattr(pulp, pulp_name, None)
        if solver_class is None:
            return False
        return solver_class().available()
    except Exception:
        return False


def get_available_solver_names() -> list[str]:
    """Return solver names in priority order that are currently available."""
    return [name for name in SOLVER_PRIORITY if is_solver_available(name)]


def solve_with_pulp(
    model: Model, decision_variables: Dict[Tuple[str, str], Variable], solver_name: str = "CBC"
) -> Solution:
    """
    Convenience function to solve a model with PuLP.

    Args:
        model: The abstract LP model to solve
        decision_variables: Dictionary mapping (distributor, product) to Variable
        solver_name: Name of the PuLP solver to use (default: "CBC")

    Returns:
        Solution object with status, objective value, and variable values

    Example:
        >>> from src.optimization import ModelBuilder, solve_with_pulp
        >>> from src.optimization.constraints import (
        ...     DistributorCoverageConstraint,
        ...     FactorySupplyConstraint,
        ...     TargetCoverageConstraint,
        ...     DeliveryHistoryConstraint,
        ...     DeliverySmoothingConstraint,
        ... )
        >>>
        >>> builder = ModelBuilder([
        ...     DistributorCoverageConstraint(),
        ...     FactorySupplyConstraint(),
        ...     TargetCoverageConstraint(),
        ...     DeliveryHistoryConstraint(),
        ...     DeliverySmoothingConstraint(),
        ... ])
        >>> result = builder.build(data)
        >>> solution = solve_with_pulp(result.model, result.decision_variables)
        >>> print(f"Status: {solution.status}")
        >>> print(f"Objective: {solution.objective_value}")
    """
    solver = PuLPSolver(solver_name=solver_name)
    return solver.solve(model, decision_variables)


def solve(
    model: Model,
    decision_variables: Dict[Tuple[str, str], Variable],
    method: str,
    *,
    data: Any = None,
) -> Solution:
    """
    Unified entry point to solve the model with any available solver.

    Args:
        model: The abstract LP model.
        decision_variables: Mapping (distributor, product) -> Variable.
        method: Solver name: "CBC", "GLPK", "Scipy", "Greedy", "SimulatedAnnealing".
        data: OptimizationData; required when method is "Greedy" or "SimulatedAnnealing".

    Returns:
        Solution with status, objective_value, variable_values.

    Raises:
        ValueError: If method is unknown or data is missing for heuristic solvers.
        RuntimeError: If the chosen solver fails.
    """
    method = method.strip()
    if method in _PULP_SOLVER_NAMES:
        solver = PuLPSolver(solver_name=method)
        return solver.solve(model, decision_variables)
    if method == "Scipy":
        if not _scipy_available():
            raise RuntimeError("Scipy solver requested but scipy is not installed")
        return ScipyLinprogSolver().solve(model, decision_variables)
    if method == "Greedy":
        if data is None:
            raise ValueError("Greedy solver requires OptimizationData (data=...)")
        from src.optimization.heuristic_solvers import GreedySolver
        return GreedySolver(data).solve(model, decision_variables)
    if method == "SimulatedAnnealing":
        if data is None:
            raise ValueError("SimulatedAnnealing solver requires OptimizationData (data=...)")
        from src.optimization.heuristic_solvers import SimulatedAnnealingSolver
        return SimulatedAnnealingSolver(data).solve(model, decision_variables)
    raise ValueError(
        f"Unknown solver: {method}. Available: {', '.join(SOLVER_PRIORITY)}"
    )

