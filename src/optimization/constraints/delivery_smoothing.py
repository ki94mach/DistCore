"""Soft constraint: delivery smoothing versus historical deliveries."""

from __future__ import annotations

from src.optimization.data import OptimizationData
from src.optimization.lp import Model, Variable, linear_sum
from src.optimization.constraints.base import Constraint, ConstraintResult


class DeliverySmoothingConstraint(Constraint):
    name = "delivery_smoothing"
    is_hard = False

    def apply(
            self, model: Model,
            data: OptimizationData,
            x: dict[tuple[str, str], Variable]
            ) -> ConstraintResult:
        result = ConstraintResult()
        lower_bound = data.settings.delivery_lower_bound
        upper_bound = data.settings.delivery_upper_bound
        weight = data.settings.weight_delivery
        for distributor in data.distributors:
            for product in data.products:
                delivery_ma = data.delivery_moving_average(distributor, product)
                slack_low = model.add_variable(
                    name=f"s_delivery_low_{distributor}_{product}",
                    low=0.0,
                )
                slack_high = model.add_variable(
                    name=f"s_delivery_high_{distributor}_{product}",
                    low=0.0,
                )
                lower_expression = linear_sum(
                    [
                        (x[(distributor, product)], 1.0),
                        (slack_low, 1.0),
                    ]
                )
                model.add_constraint(
                    lower_expression,
                    ">=",
                    lower_bound * delivery_ma,
                    name=f"delivery_low_{distributor}_{product}",
                )
                upper_expression = linear_sum(
                    [
                        (x[(distributor, product)], 1.0),
                        (slack_high, -1.0),
                    ]
                )
                model.add_constraint(
                    upper_expression,
                    "<=",
                    upper_bound * delivery_ma,
                    name=f"delivery_high_{distributor}_{product}",
                )
                result.slack_variables.append(slack_low)
                result.slack_variables.append(slack_high)
                result.objective_terms.append((slack_low, weight))
                result.objective_terms.append((slack_high, weight))
        return result
