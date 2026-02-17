"""Centralized parameter presets and helper functions for solvers and constraints.

This module provides:
1. SOLVER_PRESETS: Dictionary of solver name -> preset name -> options dict
2. CONSTRAINT_PRESETS: Dictionary of preset name -> OptimizationSettings
3. Helper functions to get default options, available presets, and merge options

Presets are loaded from YAML config file (src/optimization/config/presets.yml).
If the config file doesn't exist, falls back to hardcoded defaults.

All modules that call solvers or configure constraints should use these presets
and helpers for consistency.
"""

from __future__ import annotations

import yaml
from pathlib import Path
from typing import Any, Dict, List, Optional

# Import solver configs to get defaults
from src.optimization.solvers.simulated_annealing_solver import (
    SAConfig,
    ProblemSpecificConfig,
)
from src.optimization.data import OptimizationSettings


# ---------------------------------------------------------------------------
# Config File Loading
# ---------------------------------------------------------------------------

def _get_default_config_path() -> Path:
    """Get the default path to the presets configuration file."""
    current_file = Path(__file__)
    # param_presets.py is in src/optimization/solvers/
    # config file is in src/optimization/config/
    return current_file.parent.parent / "config" / "presets.yml"


def _load_presets_from_yaml(config_path: Optional[Path] = None) -> Dict[str, Any]:
    """Load presets from YAML configuration file.
    
    Args:
        config_path: Optional path to config file. If None, uses default path.
        
    Returns:
        Dictionary with 'solver_presets' and 'constraint_presets' keys.
        
    Raises:
        FileNotFoundError: If config file doesn't exist
        ValueError: If config structure is invalid
    """
    config_file_path = config_path or _get_default_config_path()
    
    if not config_file_path.exists():
        raise FileNotFoundError(
            f"Presets configuration file not found: {config_file_path}\n"
            f"Please create the config file or ensure it exists."
        )
    
    with open(config_file_path, 'r', encoding='utf-8') as config_file:
        config = yaml.safe_load(config_file)
    
    if not config:
        raise ValueError("Invalid presets configuration: file is empty")
    
    if 'solver_presets' not in config:
        raise ValueError("Invalid presets configuration: 'solver_presets' key not found")
    
    if 'constraint_presets' not in config:
        raise ValueError("Invalid presets configuration: 'constraint_presets' key not found")
    
    return config


def _get_fallback_solver_presets() -> Dict[str, Dict[str, Dict[str, Any]]]:
    """Get fallback solver presets (hardcoded defaults).
    
    Used when config file doesn't exist or fails to load.
    """
    return {
        "SimulatedAnnealing": {
            "default": {
                "max_iter": 5000,
                "initial_temp": 1000.0,
                "min_temp": 0.01,
                "cooling_rate": 0.995,
                "step_scale": 0.2,
                "transfer_fraction": 0.5,
                "initial_scale": 0.15,
                "decrease_bias": 0.6,
            },
            "fast": {
                "max_iter": 2000,
                "initial_temp": 500.0,
                "min_temp": 0.1,
                "cooling_rate": 0.99,
                "step_scale": 0.15,
                "transfer_fraction": 0.5,
                "initial_scale": 0.15,
                "decrease_bias": 0.6,
            },
            "thorough": {
                "max_iter": 10000,
                "initial_temp": 2000.0,
                "min_temp": 0.001,
                "cooling_rate": 0.999,
                "step_scale": 0.2,
                "transfer_fraction": 0.5,
                "initial_scale": 0.15,
                "decrease_bias": 0.6,
            },
        },
    }


def _get_fallback_constraint_presets() -> Dict[str, OptimizationSettings]:
    """Get fallback constraint presets (hardcoded defaults).
    
    Used when config file doesn't exist or fails to load.
    """
    return {
        "default": OptimizationSettings(
            coverage_ratio=1.5,
            target_coverage_ratio=1.5,
            sales_window=3,
            delivery_lower_bound=0.9,
            delivery_upper_bound=1.2,
            weight_demand=1.0,
            weight_target_units=2.0,
            weight_smoothing=1.0,
            weight_shipment=1.0,
        ),
        "focus_demand": OptimizationSettings(
            coverage_ratio=1.5,
            target_coverage_ratio=1.5,
            sales_window=3,
            delivery_lower_bound=0.9,
            delivery_upper_bound=1.2,
            weight_demand=2.0,
            weight_target_units=1.0,
            weight_smoothing=1.0,
            weight_shipment=1.0,
        ),
        "focus_targets": OptimizationSettings(
            coverage_ratio=1.5,
            target_coverage_ratio=1.5,
            sales_window=3,
            delivery_lower_bound=0.9,
            delivery_upper_bound=1.2,
            weight_demand=1.0,
            weight_target_units=2.0,
            weight_smoothing=1.0,
            weight_shipment=1.0,
        ),
        "high_coverage": OptimizationSettings(
            coverage_ratio=2.0,
            target_coverage_ratio=2.0,
            sales_window=6,
            delivery_lower_bound=0.9,
            delivery_upper_bound=1.2,
            weight_demand=1.0,
            weight_target_units=1.0,
            weight_smoothing=1.0,
            weight_shipment=1.0,
        ),
    }


# ---------------------------------------------------------------------------
# Load Presets from Config File (with fallback)
# ---------------------------------------------------------------------------

def _load_presets(config_path: Optional[Path] = None) -> tuple[Dict[str, Dict[str, Dict[str, Any]]], Dict[str, OptimizationSettings]]:
    """Load presets from YAML file, falling back to hardcoded defaults if file doesn't exist.
    
    Args:
        config_path: Optional path to config file. If None, uses default path.
        
    Returns:
        Tuple of (solver_presets_dict, constraint_presets_dict)
    """
    try:
        config = _load_presets_from_yaml(config_path)
        
        # Load solver presets
        solver_presets_raw = config.get('solver_presets', {})
        solver_presets: Dict[str, Dict[str, Dict[str, Any]]] = {}
        for solver_name, presets_dict in solver_presets_raw.items():
            solver_presets[solver_name] = {}
            for preset_name, params_dict in presets_dict.items():
                solver_presets[solver_name][preset_name] = dict(params_dict)
        
        # Load constraint presets
        constraint_presets_raw = config.get('constraint_presets', {})
        constraint_presets: Dict[str, OptimizationSettings] = {}
        for preset_name, params_dict in constraint_presets_raw.items():
            constraint_presets[preset_name] = OptimizationSettings(**params_dict)
        
        return solver_presets, constraint_presets
        
    except FileNotFoundError:
        # Fallback to hardcoded defaults
        return _get_fallback_solver_presets(), _get_fallback_constraint_presets()
    except Exception as e:
        # Log warning but use fallbacks
        import warnings
        warnings.warn(
            f"Failed to load presets from config file: {e}. Using fallback defaults.",
            UserWarning
        )
        return _get_fallback_solver_presets(), _get_fallback_constraint_presets()


# Load presets at module import time
SOLVER_PRESETS, CONSTRAINT_PRESETS = _load_presets()


def reload_presets(config_path: Optional[Path] = None) -> None:
    """Reload presets from config file.
    
    Useful for testing or when config file is modified at runtime.
    Updates the global SOLVER_PRESETS and CONSTRAINT_PRESETS variables.
    
    Args:
        config_path: Optional path to config file. If None, uses default path.
    """
    global SOLVER_PRESETS, CONSTRAINT_PRESETS
    SOLVER_PRESETS, CONSTRAINT_PRESETS = _load_presets(config_path)


# ---------------------------------------------------------------------------
# Helper Functions
# ---------------------------------------------------------------------------

def get_default_options(solver_name: str) -> Dict[str, Any]:
    """Get default options dict for a solver.
    
    This returns the options dict that would be used if no options are provided.
    For solvers with config dataclasses, this extracts defaults from the dataclass.
    For solvers without tunable parameters, returns empty dict.
    
    Args:
        solver_name: Name of the solver (e.g., "SimulatedAnnealing", "CBC")
        
    Returns:
        Dict of default option key -> default value
    """
    if solver_name == "SimulatedAnnealing":
        # Extract defaults from config dataclasses
        sa_defaults = SAConfig()
        problem_defaults = ProblemSpecificConfig()
        return {
            "max_iter": sa_defaults.max_iter,
            "initial_temp": sa_defaults.initial_temp,
            "min_temp": sa_defaults.min_temp,
            "cooling_rate": sa_defaults.cooling_rate,
            "step_scale": sa_defaults.step_scale,
            "transfer_fraction": problem_defaults.transfer_fraction,
            "initial_scale": problem_defaults.initial_scale,
            "decrease_bias": problem_defaults.decrease_bias,
        }
    
    # Other solvers don't have tunable parameters yet
    return {}


def get_available_presets(solver_name: str) -> List[str]:
    """Get list of available preset names for a solver.
    
    Args:
        solver_name: Name of the solver
        
    Returns:
        List of preset names (e.g., ["default", "fast", "thorough"])
    """
    return list(SOLVER_PRESETS.get(solver_name, {}).keys())


def get_preset_options(solver_name: str, preset_name: str) -> Optional[Dict[str, Any]]:
    """Get options dict for a specific solver preset.
    
    Args:
        solver_name: Name of the solver
        preset_name: Name of the preset (e.g., "default", "fast")
        
    Returns:
        Options dict, or None if preset doesn't exist
    """
    return SOLVER_PRESETS.get(solver_name, {}).get(preset_name)


def merge_options(
    solver_name: str,
    preset_name: Optional[str] = None,
    custom_options: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Merge default options, preset options, and custom options.
    
    Priority order (later overrides earlier):
    1. Default options (from solver config dataclass)
    2. Preset options (if preset_name provided)
    3. Custom options (if provided)
    
    Args:
        solver_name: Name of the solver
        preset_name: Optional preset name to apply
        custom_options: Optional dict of custom options to override
        
    Returns:
        Merged options dict ready to pass to solve(..., solver_options={solver_name: ...})
    """
    options = get_default_options(solver_name)
    
    if preset_name:
        preset_opts = get_preset_options(solver_name, preset_name)
        if preset_opts:
            options.update(preset_opts)
        else:
            raise ValueError(
                f"Unknown preset '{preset_name}' for solver '{solver_name}'. "
                f"Available: {get_available_presets(solver_name)}"
            )
    
    if custom_options:
        options.update(custom_options)
    
    return options


def get_solver_options_description(solver_name: str) -> Dict[str, Dict[str, Any]]:
    """Get description of all tunable options for a solver.
    
    Returns a dict mapping option name -> {"default": value, "description": str, "type": str}
    Useful for generating UI prompts or documentation.
    
    Args:
        solver_name: Name of the solver
        
    Returns:
        Dict of option_name -> {"default": ..., "description": ..., "type": ...}
    """
    if solver_name == "SimulatedAnnealing":
        return {
            "max_iter": {
                "default": 5000,
                "description": "Total iterations. Increase for better solutions and longer run time.",
                "type": "int",
            },
            "initial_temp": {
                "default": 1000.0,
                "description": "Starting temperature. Higher → more random acceptance at the start.",
                "type": "float",
            },
            "min_temp": {
                "default": 0.01,
                "description": "Stop when temperature drops below this.",
                "type": "float",
            },
            "cooling_rate": {
                "default": 0.995,
                "description": "Temperature multiplied by this each iteration. Closer to 1 → longer cooling.",
                "type": "float",
            },
            "step_scale": {
                "default": 0.2,
                "description": "Perturbation size as fraction of variable range. Larger → bigger moves, noisier.",
                "type": "float",
            },
            "transfer_fraction": {
                "default": 0.5,
                "description": "Fraction of moves that are same-product transfers (keeps supply feasible).",
                "type": "float",
            },
            "initial_scale": {
                "default": 0.15,
                "description": "Initial solution scale (1.0 = pure greedy; 0.15 = 15% of greedy allocation).",
                "type": "float",
            },
            "decrease_bias": {
                "default": 0.6,
                "description": "For single-var moves, probability of trying a decrease (helps reduce total delivery).",
                "type": "float",
            },
        }
    
    # Other solvers don't have tunable parameters yet
    return {}


# ---------------------------------------------------------------------------
# Constraint Parameter Helper Functions
# ---------------------------------------------------------------------------
# Note: CONSTRAINT_PRESETS is now loaded from YAML config file above

def get_default_settings() -> OptimizationSettings:
    """Get default OptimizationSettings.
    
    Returns:
        OptimizationSettings instance with default values
    """
    return OptimizationSettings()


def get_available_constraint_presets() -> List[str]:
    """Get list of available constraint preset names.
    
    Returns:
        List of preset names (e.g., ["default", "focus_demand", "focus_targets"])
    """
    return list(CONSTRAINT_PRESETS.keys())


def get_constraint_preset(preset_name: str) -> Optional[OptimizationSettings]:
    """Get OptimizationSettings for a specific preset.
    
    Args:
        preset_name: Name of the preset (e.g., "default", "focus_demand")
        
    Returns:
        OptimizationSettings instance, or None if preset doesn't exist
    """
    return CONSTRAINT_PRESETS.get(preset_name)


def merge_settings(
    preset_name: Optional[str] = None,
    custom_settings: Optional[Dict[str, Any]] = None,
) -> OptimizationSettings:
    """Merge default settings, preset settings, and custom settings.
    
    Priority order (later overrides earlier):
    1. Default settings (from OptimizationSettings dataclass defaults)
    2. Preset settings (if preset_name provided)
    3. Custom settings (if provided as dict)
    
    Args:
        preset_name: Optional preset name to apply
        custom_settings: Optional dict of custom settings to override
        
    Returns:
        Merged OptimizationSettings instance
    """
    # Start with defaults
    defaults = get_default_settings()
    
    # Apply preset if provided
    if preset_name:
        preset_settings = get_constraint_preset(preset_name)
        if preset_settings:
            # Create a new instance with preset values, then override with custom if any
            settings_dict = {
                "coverage_ratio": preset_settings.coverage_ratio,
                "target_coverage_ratio": preset_settings.target_coverage_ratio,
                "sales_window": preset_settings.sales_window,
                "delivery_lower_bound": preset_settings.delivery_lower_bound,
                "delivery_upper_bound": preset_settings.delivery_upper_bound,
                "weight_demand": preset_settings.weight_demand,
                "weight_target_units": preset_settings.weight_target_units,
                "weight_smoothing": preset_settings.weight_smoothing,
                "weight_shipment": preset_settings.weight_shipment,
            }
        else:
            raise ValueError(
                f"Unknown constraint preset '{preset_name}'. "
                f"Available: {get_available_constraint_presets()}"
            )
    else:
        # Start with defaults as dict
        settings_dict = {
            "coverage_ratio": defaults.coverage_ratio,
            "target_coverage_ratio": defaults.target_coverage_ratio,
            "sales_window": defaults.sales_window,
            "delivery_lower_bound": defaults.delivery_lower_bound,
            "delivery_upper_bound": defaults.delivery_upper_bound,
            "weight_demand": defaults.weight_demand,
            "weight_target_units": defaults.weight_target_units,
            "weight_smoothing": defaults.weight_smoothing,
            "weight_shipment": defaults.weight_shipment,
        }
    
    # Apply custom overrides if provided
    if custom_settings:
        settings_dict.update(custom_settings)
    
    return OptimizationSettings(**settings_dict)


def settings_from_dict(d: Dict[str, Any]) -> OptimizationSettings:
    """Build OptimizationSettings from a dict (e.g. from JSON).
    
    Args:
        d: Dictionary with OptimizationSettings fields
        
    Returns:
        OptimizationSettings instance
    """
    defaults = get_default_settings()
    return OptimizationSettings(
        coverage_ratio=float(d.get("coverage_ratio", defaults.coverage_ratio)),
        target_coverage_ratio=float(d.get("target_coverage_ratio", defaults.target_coverage_ratio)),
        sales_window=int(d.get("sales_window", defaults.sales_window)),
        delivery_lower_bound=float(d.get("delivery_lower_bound", defaults.delivery_lower_bound)),
        delivery_upper_bound=float(d.get("delivery_upper_bound", defaults.delivery_upper_bound)),
        weight_demand=float(d.get("weight_demand", defaults.weight_demand)),
        weight_target_units=float(d.get("weight_target_units", defaults.weight_target_units)),
        weight_smoothing=float(d.get("weight_smoothing", defaults.weight_smoothing)),
        weight_shipment=float(d.get("weight_shipment", defaults.weight_shipment)),
    )


def get_constraint_settings_description() -> Dict[str, Dict[str, Any]]:
    """Get description of all tunable constraint parameters.
    
    Returns a dict mapping parameter name -> {"default": value, "description": str, "type": str}
    Useful for generating UI prompts or documentation.
    
    Returns:
        Dict of parameter_name -> {"default": ..., "description": ..., "type": ...}
    """
    defaults = get_default_settings()
    return {
        "coverage_ratio": {
            "default": defaults.coverage_ratio,
            "description": "Distributor coverage ratio (SC1). Multiplier for distributor-product coverage (e.g., 1.5 = 150% of demand).",
            "type": "float",
        },
        "target_coverage_ratio": {
            "default": defaults.target_coverage_ratio,
            "description": "Target units coverage ratio (SC2). Multiplier for target units coverage (e.g., 1.5 = 150% of target).",
            "type": "float",
        },
        "sales_window": {
            "default": defaults.sales_window,
            "description": "Sales moving average window in months. Allowed values: 3 or 6.",
            "type": "int",
        },
        "delivery_lower_bound": {
            "default": defaults.delivery_lower_bound,
            "description": "Lower bound for delivery smoothing constraint (e.g., 0.9 = 90% of 6-month average).",
            "type": "float",
        },
        "delivery_upper_bound": {
            "default": defaults.delivery_upper_bound,
            "description": "Upper bound for delivery smoothing constraint (e.g., 1.2 = 120% of 6-month average).",
            "type": "float",
        },
        "weight_demand": {
            "default": defaults.weight_demand,
            "description": "Weight for demand coverage constraint violations in objective. Increase to prioritize filling demand coverage gaps.",
            "type": "float",
        },
        "weight_target_units": {
            "default": defaults.weight_target_units,
            "description": "Weight for target units constraint violations in objective. Increase to prioritize hitting product targets.",
            "type": "float",
        },
        "weight_smoothing": {
            "default": defaults.weight_smoothing,
            "description": "Weight for delivery smoothing constraint violations in objective. Increase to prioritize stable deliveries.",
            "type": "float",
        },
        "weight_shipment": {
            "default": defaults.weight_shipment,
            "description": "Weight for decision variables in objective (penalizes unnecessary shipping). Increase to ship less; decrease for more flexibility.",
            "type": "float",
        },
    }
