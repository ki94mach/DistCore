"""Soft constraint: product total coverage versus target units."""

from __future__ import annotations

from src.optimization.data import OptimizationData
from src.optimization.lp import Model, Variable, linear_sum
from src.optimization.constraints.base import Constraint, ConstraintResult


class ProductTargetUnitsConstraint(Constraint):
    name = "product_target_units"
    is_hard = False

    def apply(
            self, model: Model,
            data: OptimizationData,
            x: dict[tuple[str, str], Variable]
            ) -> ConstraintResult:
        result = ConstraintResult()
        ratio = data.settings.target_coverage_ratio
        for product in data.products:
            slack = model.add_variable(
                name=f"s_units_{product}",
                low=0.0,
            )
            terms = [
                (x[(distributor, product)], 1.0)
                for distributor in data.distributors
                ]
            total_inventory = sum(
                data.inventory(distributor, product) 
                for distributor in data.distributors
                )
            expression = linear_sum(terms + [(slack, 1.0)], constant=total_inventory)
            model.add_constraint(
                expression,
                ">=",
                ratio * data.remaining_target_units(product),
                name=f"target_units_{product}",
            )
            result.slack_variables.append(slack)
            result.objective_terms.append((slack, data.settings.weight_target_units))
        return result
        