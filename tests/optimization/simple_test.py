"""Simple standalone test - reads source files directly and patches imports.

Run from project root: python tests/optimization/simple_test.py
"""

import sys
from pathlib import Path

# Add paths
project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root / "src"))

# Read and execute source files with import fixes
def exec_file_with_fixes(filepath, globals_dict):
    """Execute a Python file with import fixes."""
    with open(filepath, 'r', encoding='utf-8') as f:
        code = f.read()
    
    # Fix relative imports
    code = code.replace('from ..data import', 'from optimization.data import')
    code = code.replace('from ..lp import', 'from optimization.lp import')
    code = code.replace('from base import', 'from optimization.constraints.base import')
    code = code.replace('from data import', 'from optimization.data import')
    code = code.replace('from lp import', 'from optimization.lp import')
    code = code.replace('from constraints.base import', 'from optimization.constraints.base import')
    
    exec(compile(code, filepath, 'exec'), globals_dict)

# Create namespace
namespace = {'__name__': '__main__'}

# Load in order
opt_dir = project_root / "src" / "optimization"
exec_file_with_fixes(opt_dir / "lp.py", namespace)
exec_file_with_fixes(opt_dir / "data.py", namespace)

# Create optimization package structure
namespace['optimization'] = type('module', (), {})()
namespace['optimization'].data = namespace
namespace['optimization'].lp = namespace
namespace['optimization'].constraints = type('module', (), {})()

exec_file_with_fixes(opt_dir / "constraints" / "base.py", namespace)
namespace['optimization'].constraints.base = namespace

exec_file_with_fixes(opt_dir / "constraints" / "factory_supply.py", namespace)
exec_file_with_fixes(opt_dir / "constraints" / "distributor_coverage.py", namespace)
exec_file_with_fixes(opt_dir / "constraints" / "target_coverage.py", namespace)
exec_file_with_fixes(opt_dir / "builder.py", namespace)

# Extract classes
Variable = namespace['Variable']
LinearExpression = namespace['LinearExpression']
Model = namespace['Model']
OptimizationData = namespace['OptimizationData']
OptimizationSettings = namespace['OptimizationSettings']
ModelBuilder = namespace['ModelBuilder']
FactorySupplyConstraint = namespace['FactorySupplyConstraint']
DistributorCoverageConstraint = namespace['DistributorCoverageConstraint']
ProductTargetUnitsConstraint = namespace['ProductTargetUnitsConstraint']

# Run test
print("=" * 60)
print("OPTIMIZATION MODULE SIMPLE TEST")
print("=" * 60)

# Create test data
print("\n1. Creating test data...")
settings = OptimizationSettings(
    coverage_ratio=1.5,
    sales_window=6,
    weight_coverage=1.0,
    weight_target_units=1.0
)

data = OptimizationData(
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

# Test methods
print("\n2. Testing data methods...")
assert data.inventory("D1", "P1") == 10.0
assert data.factory_supply("P1") == 100.0
assert data.coverage_demand("D1", "P1") == 45.0
print("   ✓ All data methods working")

# Build model
print("\n3. Building model...")
constraints = [
    FactorySupplyConstraint(),
    DistributorCoverageConstraint(),
    ProductTargetUnitsConstraint()
]
builder = ModelBuilder(constraints)
result = builder.build(data)
print("   ✓ Model built")

# Verify
print("\n4. Model structure:")
print(f"   Decision variables: {len(result.decision_variables)}")
print(f"   Total variables: {len(result.model.variables)}")
print(f"   Constraints: {len(result.model.constraints)}")
print(f"   Objective: {result.model.objective.sense}")

print("\n" + "=" * 60)
print("✓ TEST PASSED!")
print("=" * 60)

