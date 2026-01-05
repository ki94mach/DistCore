"""Constraint base classes."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Tuple

from ..data import OptimizationData
from ..lp import Model, Variable


@dataclass
class ConstraintResult:
    objective_terms: List[Tuple[Variable, float]] = field(default_factory=list)
    slack_variables: List[Variable] = field(default_factory=list)


class Constraint:
    name: str
    is_hard: bool = False

    def apply(self, model: Model, data: OptimizationData, x: dict[tuple[str, str], Variable]) -> ConstraintResult:
        raise NotImplementedError
        