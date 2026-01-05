"""Hard constraint: factory supply feasibility."""

from __future__ import annotations

from src.optimization.data import OptimizationData
from src.optimization.lp import Model, Variable, linear_sum
from src.optimization.constraints.base import Constraint, ConstraintResult


class FactorySupplyConstraint(Constraint):
    name = "factory_supply"
    is_hard = True

    def apply(self, model: Model, data: OptimizationData, x: dict[tuple[str, str], Variable]) -> ConstraintResult:
        for product in data.products:
            terms = [(x[(distributor, product)], 1.0) for distributor in data.distributors]
            expression = linear_sum(terms)
            model.add_constraint(
                expression,
                "<=",
                data.factory_supply(product),
                name=f"factory_supply_{product}",
            )
        return ConstraintResult()
        