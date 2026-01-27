"""Soft constraint: distributor-product coverage versus sales."""

from __future__ import annotations

from src.optimization.data import OptimizationData
from src.optimization.lp import Model, Variable, linear_sum
from src.optimization.constraints.base import Constraint, ConstraintResult


class DistributorCoverageConstraint(Constraint):
    name = "distributor_coverage"
    is_hard = False

    def apply(
            self, model: Model,
            data: OptimizationData,
            x: dict[tuple[str, str], Variable]
            ) -> ConstraintResult:
        result = ConstraintResult()
        ratio = data.settings.coverage_ratio
        for distributor in data.distributors:
            for product in data.products:
                demand = data.coverage_demand(distributor, product)
                slack = model.add_variable(
                    name=f"s_coverage_{distributor}_{product}",
                    low=0.0,
                )
                on_hand = data.inventory(distributor, product)
                expression = linear_sum(
                    [
                        (x[(distributor, product)], 1.0),
                        (slack, 1.0),
                    ],
                    constant=on_hand,
                )
                model.add_constraint(
                    expression,
                    ">=",
                    ratio * demand,
                    name=f"coverage_{distributor}_{product}",
                )
                result.slack_variables.append(slack)
                result.objective_terms.append((slack, data.settings.weight_coverage))
        return result
        