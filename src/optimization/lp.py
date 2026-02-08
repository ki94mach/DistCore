"""Minimal linear programming model representation.

This module intentionally avoids coupling to any external solver so the
optimization layer can evolve without immediate dependency decisions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Tuple


@dataclass(frozen=True)
class Variable:
    name: str
    low: float = 0.0
    up: Optional[float] = None


@dataclass
class LinearExpression:
    coefficients: Dict[Variable, float] = field(default_factory=dict)
    constant: float = 0.0

    def add_term(self, variable: Variable, coefficient: float) -> None:
        self.coefficients[variable] = self.coefficients.get(variable, 0.0) + coefficient


@dataclass
class Constraint:
    expression: LinearExpression
    sense: str
    rhs: float
    name: str


@dataclass
class Objective:
    expression: LinearExpression
    sense: str = "min"


@dataclass
class Model:
    variables: List[Variable] = field(default_factory=list)
    constraints: List[Constraint] = field(default_factory=list)
    objective: Optional[Objective] = None

    def add_variable(self, name: str, low: float = 0.0, up: Optional[float] = None) -> Variable:
        variable = Variable(name=name, low=low, up=up)
        self.variables.append(variable)
        return variable

    def add_constraint(self, expression: LinearExpression, sense: str, rhs: float, name: str) -> None:
        if sense not in {"<=", ">=", "="}:
            raise ValueError(f"Unsupported constraint sense: {sense}")
        self.constraints.append(Constraint(expression=expression, sense=sense, rhs=rhs, name=name))

    def set_objective(self, expression: LinearExpression, sense: str = "min") -> None:
        if sense not in {"min", "max"}:
            raise ValueError(f"Unsupported objective sense: {sense}")
        self.objective = Objective(expression=expression, sense=sense)


def linear_sum(terms: Iterable[Tuple[Variable, float]], constant: float = 0.0) -> LinearExpression:
    expression = LinearExpression(constant=constant)
    for variable, coefficient in terms:
        expression.add_term(variable, coefficient)
    return expression


def evaluate_expression(
    expression: LinearExpression, variable_values: Dict[Variable, float]
) -> float:
    """Evaluate a linear expression at the given variable values."""
    value = expression.constant
    for var, coeff in expression.coefficients.items():
        value += coeff * variable_values.get(var, 0.0)
    return value


def evaluate_objective(model: Model, variable_values: Dict[Variable, float]) -> float:
    """Evaluate the model objective at the given variable values. Returns 0.0 if no objective."""
    if model.objective is None:
        return 0.0
    return evaluate_expression(model.objective.expression, variable_values)


def is_feasible(
    model: Model, variable_values: Dict[Variable, float], tol: float = 1e-6
) -> bool:
    """Check if variable values satisfy all constraints and variable bounds."""
    for var in model.variables:
        v = variable_values.get(var, 0.0)
        if v < var.low - tol:
            return False
        if var.up is not None and v > var.up + tol:
            return False
    for constraint in model.constraints:
        lhs = evaluate_expression(constraint.expression, variable_values)
        if constraint.sense == "<=" and lhs > constraint.rhs + tol:
            return False
        if constraint.sense == ">=" and lhs < constraint.rhs - tol:
            return False
        if constraint.sense == "=" and abs(lhs - constraint.rhs) > tol:
            return False
    return True
