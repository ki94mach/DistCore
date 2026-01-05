"""Optimization model builder for the initial LP formulation."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, List, Tuple

from .constraints.base import Constraint, ConstraintResult
from .data import OptimizationData
from .lp import LinearExpression, Model, Variable, linear_sum


@dataclass
class ModelBuildResult:
    model: Model
    decision_variables: dict[tuple[str, str], Variable]
    slack_variables: List[Variable] = field(default_factory=list)


class ModelBuilder:
    def __init__(self, constraints: Iterable[Constraint]) -> None:
        self.constraints = list(constraints)

    def build(self, data: OptimizationData) -> ModelBuildResult:
        model = Model()
        decision_variables = self._create_decision_variables(model, data)
        objective_terms: List[Tuple[Variable, float]] = []
        slack_variables: List[Variable] = []

        for constraint in self.constraints:
            result = constraint.apply(model, data, decision_variables)
            objective_terms.extend(result.objective_terms)
            slack_variables.extend(result.slack_variables)

        model.set_objective(self._build_objective(objective_terms), sense="min")
        return ModelBuildResult(
            model=model,
            decision_variables=decision_variables,
            slack_variables=slack_variables,
        )

    def _create_decision_variables(
        self, model: Model, data: OptimizationData
    ) -> dict[tuple[str, str], Variable]:
        decision_variables: dict[tuple[str, str], Variable] = {}
        for distributor in data.distributors:
            for product in data.products:
                variable = model.add_variable(name=f"x_{distributor}_{product}", low=0.0)
                decision_variables[(distributor, product)] = variable
        return decision_variables

    def _build_objective(self, objective_terms: List[Tuple[Variable, float]]) -> LinearExpression:
        return linear_sum([(variable, weight) for variable, weight in objective_terms])
