"""Hard constraint: disallow deliveries without recent history."""

from __future__ import annotations

from src.optimization.data import OptimizationData
from src.optimization.lp import Model, Variable, linear_sum
from src.optimization.constraints.base import Constraint, ConstraintResult


class DeliveryHistoryConstraint(Constraint):
    name = "delivery_history"
    is_hard = True

    def apply(
            self, model: Model,
            data: OptimizationData,
            x: dict[tuple[str, str], Variable]
            ) -> ConstraintResult:
        for distributor in data.distributors:
            for product in data.products:
                if data.has_recent_delivery(distributor, product):
                    continue
                expression = linear_sum([(x[(distributor, product)], 1.0)])
                model.add_constraint(
                    expression,
                    "<=",
                    0.0,
                    name=f"delivery_history_{distributor}_{product}",
                )
        return ConstraintResult()
