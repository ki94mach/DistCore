"""Soft objective term: penalize total shipment to regularize the solution.

Adds ``weight_shipment * x(d, p)`` to the objective for every decision variable.
Since the model minimizes, this discourages unnecessary shipping and acts as a
tiebreaker when multiple solutions satisfy the soft constraints equally well.
"""

from __future__ import annotations

from src.optimization.data import OptimizationData
from src.optimization.lp import Model, Variable
from src.optimization.constraints.base import Constraint, ConstraintResult


class ShipmentMinimizationConstraint(Constraint):
    """Regularizer that adds decision variables directly to the objective.

    Without this term the optimizer has no preference about how much to ship —
    it only minimizes slack penalties. Adding ``weight_shipment * Σ x(d,p)``
    ensures the solver ships only what is needed to satisfy the other
    constraints.
    """

    name = "shipment_minimization"
    is_hard = False

    def apply(
        self,
        model: Model,
        data: OptimizationData,
        x: dict[tuple[str, str], Variable],
    ) -> ConstraintResult:
        result = ConstraintResult()
        weight = data.settings.weight_shipment
        for distributor in data.distributors:
            for product in data.products:
                result.objective_terms.append((x[(distributor, product)], weight))
        return result
