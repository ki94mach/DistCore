"""Solvers, presets, and defaults discovery endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from src.optimization.solvers import (
    SOLVER_PRIORITY,
    get_available_constraint_presets,
    get_available_solver_names,
    get_constraint_preset,
    get_constraint_settings_description,
    get_default_options,
    get_default_settings,
    is_solver_available,
)

router = APIRouter(tags=["meta"])


@router.get("/solvers")
def list_solvers() -> dict[str, Any]:
    available = set(get_available_solver_names())
    return {
        "priority": list(SOLVER_PRIORITY),
        "available": list(available),
        "solvers": [
            {
                "name": name,
                "available": name in available or is_solver_available(name),
            }
            for name in SOLVER_PRIORITY
        ],
    }


@router.get("/presets")
def list_presets() -> dict[str, Any]:
    names = get_available_constraint_presets()
    presets = []
    for name in names:
        settings = get_constraint_preset(name)
        presets.append(
            {
                "name": name,
                "settings": settings.__dict__ if settings is not None else None,
            }
        )
    return {
        "presets": presets,
        "descriptions": get_constraint_settings_description(),
    }


@router.get("/defaults")
def list_defaults() -> dict[str, Any]:
    settings = get_default_settings()
    solver_options = {
        name: get_default_options(name)
        for name in SOLVER_PRIORITY
        if get_default_options(name)
    }
    return {
        "settings": settings.__dict__,
        "solver_options": solver_options,
    }
