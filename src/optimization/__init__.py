"""Optimization layer primitives, constraint framework, and solver registry."""

from src.optimization.builder import ModelBuilder
from src.optimization.data import OptimizationData, OptimizationSettings
from src.optimization.loader import SnapshotDataLoader
from src.optimization.lp import Constraint, LinearExpression, Model, Variable

# Solver public API (canonical location: src.optimization.solvers)
from src.optimization.solvers import (
    SOLVER_PRIORITY,
    Solution,
    get_available_solver_names,
    get_solver,
    is_solver_available,
    solve,
)
from src.optimization.solvers.base import BaseSolver
from src.optimization.solvers.pulp_solver import CBCSolver, GLPKSolver, PuLPSolver
from src.optimization.solvers.scipy_solver import ScipyLinprogSolver, ScipySolver
from src.optimization.solvers.greedy_solver import GreedySolver
from src.optimization.solvers.simulated_annealing_solver import SimulatedAnnealingSolver
from src.optimization.errors import (
    DatabaseUnavailableError,
    InvalidRunRequestError,
    MissingSnapshotError,
    OptimizationServiceError,
    SolverUnavailableError,
)
from src.optimization.service import (
    OptimizationService,
    RunRequest,
    RunResult,
    RunSummary,
    Shipment,
    TabularData,
)


def solve_with_pulp(model, decision_variables, solver_name="CBC"):
    """Convenience wrapper -- solve with a PuLP backend."""
    return PuLPSolver(solver_name=solver_name).solve(model, decision_variables)

__all__ = [
    # LP model
    "Constraint",
    "LinearExpression",
    "Model",
    "Variable",
    # Data
    "OptimizationData",
    "OptimizationSettings",
    # Application service
    "OptimizationService",
    "RunRequest",
    "RunResult",
    "RunSummary",
    "Shipment",
    "TabularData",
    # Service errors
    "OptimizationServiceError",
    "InvalidRunRequestError",
    "MissingSnapshotError",
    "SolverUnavailableError",
    "DatabaseUnavailableError",
    # Builder / Loader
    "ModelBuilder",
    "SnapshotDataLoader",
    # Solver base + registry
    "BaseSolver",
    "Solution",
    "SOLVER_PRIORITY",
    "get_available_solver_names",
    "get_solver",
    "is_solver_available",
    "solve",
    "solve_with_pulp",
    # Solver classes
    "CBCSolver",
    "GLPKSolver",
    "PuLPSolver",
    "ScipyLinprogSolver",
    "ScipySolver",
    "GreedySolver",
    "SimulatedAnnealingSolver",
]
