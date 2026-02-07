"""Solver integration for the optimization layer.

This module provides adapters to convert the abstract LP model to solver-specific
formats and solve optimization problems.

Recommended solver: PuLP (Python Linear Programming)
- Easy to use and well-documented
- Open source with CBC solver included
- Supports commercial solvers (CPLEX, Gurobi) if available
- Good for linear programming problems

Installation: pip install pulp
"""

from __future__ import annotations

import pulp
from dataclasses import dataclass
from typing import Dict, Optional, Tuple

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
                - "CPLEX" - IBM CPLEX (requires license)
                - "GUROBI" - Gurobi Optimizer (requires license)
                - "PULP_CBC_CMD" - CBC via command line
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
            "CPLEX": pulp.CPLEX_CMD(msg=0),
            "GUROBI": pulp.GUROBI_CMD(msg=0),
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
    "CPLEX": "CPLEX_CMD",
    "GUROBI": "GUROBI_CMD",
}


def is_solver_available(solver_name: str) -> bool:
    """
    Check if a solver is available on this system (executable on PATH or installed).

    Args:
        solver_name: One of "CBC", "GLPK", "CPLEX", "GUROBI"

    Returns:
        True if the solver can be executed, False otherwise.
    """
    pulp_name = _PULP_SOLVER_NAMES.get(solver_name.upper())
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
    """Return list of solver names that are currently available (e.g. ['CBC', 'GLPK'])."""
    return [name for name in _PULP_SOLVER_NAMES if is_solver_available(name)]


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

