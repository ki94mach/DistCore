"""Solver registry and public API for the optimization layer.

Mirrors the constraint pattern: each solver is a class with ``name``,
``category``, ``is_available()``, and ``solve()``.  The registry maintains
solvers in **priority order** (exact LP first, then heuristic/metaheuristic).

Solver priority for evaluation (best first):
  1. CBC              – Exact LP (PuLP); recommended reference.
  2. GLPK             – Exact LP (PuLP); alternative to CBC.
  3. Scipy            – Exact LP (HiGHS); no PuLP binary needed.
  4. Greedy           – Heuristic baseline; no deps, very fast.
  5. SimulatedAnnealing – Metaheuristic; better quality than greedy.
"""

from __future__ import annotations

from collections import OrderedDict
from typing import Any, Dict, List, Optional, Tuple, Type

from src.optimization.lp import Model, Variable
from src.optimization.solvers.base import BaseSolver, Solution

# Solver implementations
from src.optimization.solvers.pulp_solver import CBCSolver, GLPKSolver, PuLPSolver
from src.optimization.solvers.scipy_solver import ScipyLinprogSolver, ScipySolver
from src.optimization.solvers.greedy_solver import GreedySolver
from src.optimization.solvers.simulated_annealing_solver import SimulatedAnnealingSolver

# Presets and parameter management
from src.optimization.solvers.param_presets import (
    # Solver presets
    SOLVER_PRESETS,
    get_default_options,
    get_available_presets,
    get_preset_options,
    merge_options,
    get_solver_options_description,
    # Constraint presets
    CONSTRAINT_PRESETS,
    get_default_settings,
    get_available_constraint_presets,
    get_constraint_preset,
    merge_settings,
    settings_from_dict,
    get_constraint_settings_description,
)

# ---------------------------------------------------------------------------
# Registry (insertion order = priority)
# ---------------------------------------------------------------------------

_REGISTRY: Dict[str, Type[BaseSolver]] = OrderedDict()


def register(cls: Type[BaseSolver]) -> Type[BaseSolver]:
    """Add a solver class to the global registry.

    Can be used as a decorator::

        @register
        class MySolver(BaseSolver):
            name = "MySolver"
            ...
    """
    _REGISTRY[cls.name] = cls
    return cls


# Register built-in solvers in priority order
register(CBCSolver)
register(GLPKSolver)
# register(ScipySolver)
register(GreedySolver)
register(SimulatedAnnealingSolver)

# Derived from registry insertion order
SOLVER_PRIORITY: List[str] = list(_REGISTRY.keys())


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------

def is_solver_available(name: str) -> bool:
    """Check if a solver is available on this system.

    Args:
        name: One of the registered solver names (e.g. ``"CBC"``, ``"Greedy"``).

    Returns:
        ``True`` if the solver can be used, ``False`` otherwise.
    """
    cls = _REGISTRY.get(name.strip())
    if cls is None:
        return False
    return cls.is_available()


def get_available_solver_names() -> List[str]:
    """Return solver names in priority order that are currently available."""
    return [name for name, cls in _REGISTRY.items() if cls.is_available()]


def get_solver(name: str) -> BaseSolver:
    """Instantiate a solver by name.

    Raises:
        ValueError: If the solver name is not registered.
    """
    cls = _REGISTRY.get(name.strip())
    if cls is None:
        raise ValueError(
            f"Unknown solver: {name}. Available: {', '.join(SOLVER_PRIORITY)}"
        )
    return cls()


def solve(
    model: Model,
    decision_variables: Dict[Tuple[str, str], Variable],
    method: str,
    *,
    data: Any = None,
    solver_options: Optional[Dict[str, Dict[str, Any]]] = None,
) -> Solution:
    """Unified entry point to solve the model with any registered solver.

    Args:
        model: The abstract LP model.
        decision_variables: Mapping ``(distributor, product) -> Variable``.
        method: Solver name (e.g. ``"CBC"``, ``"Greedy"``, ``"SimulatedAnnealing"``).
        data: ``OptimizationData``; required for heuristic/metaheuristic solvers.
        solver_options: Optional solver-specific options keyed by solver name,
            e.g. ``{"SimulatedAnnealing": {"max_iter": 10000}}``.

    Returns:
        Solution with status, objective_value, variable_values.

    Raises:
        ValueError: If *method* is unknown or *data* is missing for heuristic solvers.
        RuntimeError: If the chosen solver is not available or fails.
    """
    method = method.strip()
    solver = get_solver(method)
    if not solver.__class__.is_available():
        raise RuntimeError(f"{method} solver is not available")
    opts = (solver_options or {}).get(method) or {}
    return solver.solve(model, decision_variables, data=data, options=opts)


__all__ = [
    # Base
    "BaseSolver",
    "Solution",
    # Solver classes
    "CBCSolver",
    "GLPKSolver",
    "PuLPSolver",
    # "ScipySolver",
    "ScipyLinprogSolver",
    "GreedySolver",
    "SimulatedAnnealingSolver",
    # Registry
    "register",
    "SOLVER_PRIORITY",
    # Functions
    "get_available_solver_names",
    "get_solver",
    "is_solver_available",
    "solve",
    # Presets and parameter management (solver)
    "SOLVER_PRESETS",
    "get_default_options",
    "get_available_presets",
    "get_preset_options",
    "merge_options",
    "get_solver_options_description",
    # Presets and parameter management (constraints)
    "CONSTRAINT_PRESETS",
    "get_default_settings",
    "get_available_constraint_presets",
    "get_constraint_preset",
    "merge_settings",
    "settings_from_dict",
    "get_constraint_settings_description",
]
