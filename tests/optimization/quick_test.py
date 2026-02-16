"""Quick test script for the optimization module.

This script can be run directly and works around import issues.
Run from project root: python tests/optimization/quick_test.py
"""

import sys
from pathlib import Path
import importlib.util
from unittest.mock import MagicMock

# Add project root to path
project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "src"))

opt_dir = project_root / "src" / "optimization"

# Load modules with import patching
def load_module_with_patches(name, path, patches=None):
    """Load a module and apply patches to fix imports."""
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    
    # Apply patches before loading
    if patches:
        for attr, value in patches.items():
            setattr(module, attr, value)
    
    spec.loader.exec_module(module)
    return module

# Load lp and data first (no relative imports)
lp = load_module_with_patches("lp", opt_dir / "lp.py")
data = load_module_with_patches("data", opt_dir / "data.py")

# Create a mock parent package for relative imports
optimization_pkg = MagicMock()
optimization_pkg.data = data
optimization_pkg.lp = lp
sys.modules["optimization"] = optimization_pkg
sys.modules["optimization.data"] = data
sys.modules["optimization.lp"] = lp

# Load base constraint with patches
base = load_module_with_patches(
    "base",
    opt_dir / "constraints" / "base.py",
    patches={
        "OptimizationData": data.OptimizationData,
        "Model": lp.Model,
        "Variable": lp.Variable
    }
)
sys.modules["optimization.constraints"] = MagicMock()
sys.modules["optimization.constraints.base"] = base

# Load constraints
factory_supply = load_module_with_patches(
    "factory_supply",
    opt_dir / "constraints" / "factory_supply.py",
    patches={
        "OptimizationData": data.OptimizationData,
        "Model": lp.Model,
        "Variable": lp.Variable,
        "linear_sum": lp.linear_sum,
        "Constraint": base.Constraint,
        "ConstraintResult": base.ConstraintResult
    }
)

demand_coverage = load_module_with_patches(
    "demand_coverage",
    opt_dir / "constraints" / "demand_coverage.py",
    patches={
        "OptimizationData": data.OptimizationData,
        "Model": lp.Model,
        "Variable": lp.Variable,
        "linear_sum": lp.linear_sum,
        "Constraint": base.Constraint,
        "ConstraintResult": base.ConstraintResult
    }
)

target_coverage = load_module_with_patches(
    "target_coverage",
    opt_dir / "constraints" / "target_coverage.py",
    patches={
        "OptimizationData": data.OptimizationData,
        "Model": lp.Model,
        "Variable": lp.Variable,
        "linear_sum": lp.linear_sum,
        "Constraint": base.Constraint,
        "ConstraintResult": base.ConstraintResult
    }
)

# Load builder
builder = load_module_with_patches(
    "builder",
    opt_dir / "builder.py",
    patches={
        "Constraint": base.Constraint,
        "ConstraintResult": base.ConstraintResult,
        "OptimizationData": data.OptimizationData,
        "LinearExpression": lp.LinearExpression,
        "Model": lp.Model,
        "Variable": lp.Variable,
        "linear_sum": lp.linear_sum
    }
)


def test_basic_functionality():
    """Test basic optimization functionality."""
    print("=" * 60)
    print("OPTIMIZATION MODULE QUICK TEST")
    print("=" * 60)
    
    # Create test data
    print("\n1. Creating test data...")
    settings = data.OptimizationSettings(
        coverage_ratio=1.5,
        target_coverage_ratio=1.5,
        sales_window=6,
        weight_coverage=1.0,
        weight_target_units=1.0
    )
    
    opt_data = data.OptimizationData(
        distributors=["D1", "D2"],
        products=["P1"],
        factory_inventory={"P1": 100.0},
        distributor_inventory={("D1", "P1"): 10.0, ("D2", "P1"): 20.0},
        sales_ma_3={},
        sales_ma_6={("D1", "P1"): 50.0, ("D2", "P1"): 30.0},
        sales_mtd={("D1", "P1"): 5.0, ("D2", "P1"): 10.0},
        target_units={"P1": 200.0},
        settings=settings
    )
    print("   ✓ Test data created")
    
    # Test data methods
    print("\n2. Testing data helper methods...")
    assert opt_data.inventory("D1", "P1") == 10.0, "Inventory check failed"
    assert opt_data.factory_supply("P1") == 100.0, "Factory supply check failed"
    assert opt_data.coverage_demand("D1", "P1") == 45.0, "Coverage demand check failed"  # 50 - 5
    print("   ✓ All data methods working")
    
    # Build model
    print("\n3. Building optimization model...")
    constraints = [
        factory_supply.FactorySupplyConstraint(),
        demand_coverage.DemandCoverageConstraint(),
        target_coverage.ProductTargetUnitsConstraint()
    ]
    model_builder = builder.ModelBuilder(constraints)
    result = model_builder.build(opt_data)
    print("   ✓ Model built successfully")
    
    # Verify model structure
    print("\n4. Verifying model structure...")
    assert len(result.decision_variables) == 2, "Should have 2 decision variables"
    assert len(result.model.variables) > 2, "Should have decision + slack variables"
    assert len(result.model.constraints) > 0, "Should have constraints"
    assert result.model.objective is not None, "Should have objective"
    print(f"   ✓ Decision variables: {len(result.decision_variables)}")
    print(f"   ✓ Total variables: {len(result.model.variables)}")
    print(f"   ✓ Constraints: {len(result.model.constraints)}")
    print(f"   ✓ Objective: {result.model.objective.sense}")
    
    print("\n" + "=" * 60)
    print("✓ ALL TESTS PASSED!")
    print("=" * 60)
    print("\nNext steps:")
    print("1. Run example_usage.py for a detailed example")
    print("2. Review the model structure")
    print("3. Integrate with a solver to get solutions")


if __name__ == "__main__":
    try:
        test_basic_functionality()
    except Exception as e:
        print(f"\n✗ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
