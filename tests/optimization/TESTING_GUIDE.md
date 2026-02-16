# How to Start Testing the Optimization Module

## Overview

The optimization module creates linear programming models for distribution optimization. This guide shows you how to test it.

## Quick Start: Manual Testing

The easiest way to start is to create a simple test script. Here's a working example:

### Step 1: Create a Test Script

Create a file `test_manual.py` in the project root:

```python
"""Manual test script for optimization module."""

import sys
from pathlib import Path

# Add src to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root / "src"))

# Import modules directly (bypassing __init__.py issues)
# Note: You may need to fix imports in the source files first
# or use importlib to load modules directly

# For now, let's test the core concepts:

# 1. Test LP primitives
print("Testing LP Model Primitives...")
print("=" * 60)

# You can test by importing and using the classes directly
# Once import issues are resolved, use:
# from optimization.lp import Variable, Model, LinearExpression
# from optimization.data import OptimizationData, OptimizationSettings
# etc.

print("\nTo test the optimization module:")
print("1. Fix import issues in src/optimization/ files")
print("2. Or use the example_usage.py script (after fixing imports)")
print("3. Or integrate with a solver library like PuLP")
```

### Step 2: Fix Import Issues (Recommended)

The optimization module has some import inconsistencies. To make testing easier, consider:

1. **Option A: Fix imports in source files** - Update relative imports to be consistent
2. **Option B: Use a test environment** - Set up proper package structure
3. **Option C: Use direct file imports** - Import files directly without package structure

### Step 3: Test Core Functionality

Once imports work, test these components:

#### Test 1: LP Model Primitives

```python
from optimization.lp import Variable, Model, LinearExpression

# Create a variable
var = Variable(name="x1", low=0.0, up=100.0)
assert var.name == "x1"
assert var.low == 0.0
assert var.up == 100.0

# Create a model
model = Model()
var1 = model.add_variable("x1", low=0.0)
var2 = model.add_variable("x2", low=0.0)

# Create a constraint
from optimization.lp import linear_sum
expr = linear_sum([(var1, 1.0), (var2, 2.0)], constant=0.0)
model.add_constraint(expr, "<=", 10.0, "c1")

assert len(model.variables) == 2
assert len(model.constraints) == 1
```

#### Test 2: Optimization Data

```python
from optimization.data import OptimizationData, OptimizationSettings

settings = OptimizationSettings(
    coverage_ratio=1.5,
    target_coverage_ratio=1.5,
    sales_window=6,
    weight_demand=1.0,
    weight_target_units=1.0
)

data = OptimizationData(
    distributors=["D1", "D2"],
    products=["P1"],
    factory_inventory={"P1": 100.0},
    distributor_inventory={("D1", "P1"): 10.0},
    sales_ma_3={},
    sales_ma_6={("D1", "P1"): 50.0},
    sales_mtd={("D1", "P1"): 5.0},
    target_units={"P1": 200.0},
    settings=settings
)

# Test helper methods
assert data.inventory("D1", "P1") == 10.0
assert data.factory_supply("P1") == 100.0
assert data.coverage_demand("D1", "P1") == 45.0  # 50 - 5
```

#### Test 3: Build a Model

```python
from optimization.builder import ModelBuilder
from optimization.constraints.factory_supply import FactorySupplyConstraint
from optimization.constraints.demand_coverage import DemandCoverageConstraint
from optimization.constraints.target_coverage import ProductTargetUnitsConstraint

# Create constraints
constraints = [
    FactorySupplyConstraint(),
    DemandCoverageConstraint(),
    ProductTargetUnitsConstraint()
]

# Build model
builder = ModelBuilder(constraints)
result = builder.build(data)

# Verify structure
assert len(result.decision_variables) > 0
assert len(result.model.variables) > 0
assert len(result.model.constraints) > 0
assert result.model.objective is not None

print(f"Decision variables: {len(result.decision_variables)}")
print(f"Total variables: {len(result.model.variables)}")
print(f"Constraints: {len(result.model.constraints)}")
```

## Testing Checklist

- [ ] **LP Model Primitives**
  - [ ] Variable creation with bounds
  - [ ] Linear expression building
  - [ ] Constraint creation
  - [ ] Model structure

- [ ] **Data Models**
  - [ ] OptimizationSettings
  - [ ] OptimizationData creation
  - [ ] Helper methods (inventory, sales, coverage_demand, etc.)

- [ ] **Constraints**
  - [ ] FactorySupplyConstraint (hard constraint)
  - [ ] DemandCoverageConstraint (soft constraint)
  - [ ] ProductTargetUnitsConstraint (soft constraint)

- [ ] **Model Builder**
  - [ ] Decision variable creation
  - [ ] Constraint application
  - [ ] Objective function construction

- [ ] **End-to-End**
  - [ ] Complete model building
  - [ ] Model structure verification
  - [ ] Constraint verification

## Example Test Data

Here's a realistic test dataset:

```python
settings = OptimizationSettings(
    coverage_ratio=1.5,           # Distributor coverage: 1.5x demand
    target_coverage_ratio=1.5,   # Target units coverage: 1.5x target
    sales_window=6,               # Use 6-month moving average
    weight_demand=1.0,         # Weight for demand coverage slack
    weight_target_units=2.0       # Weight for target units slack
)

data = OptimizationData(
    distributors=["DistributorA", "DistributorB", "DistributorC"],
    products=["ProductX", "ProductY"],
    factory_inventory={
        "ProductX": 1000.0,
        "ProductY": 800.0
    },
    distributor_inventory={
        ("DistributorA", "ProductX"): 100.0,
        ("DistributorA", "ProductY"): 50.0,
        ("DistributorB", "ProductX"): 80.0,
        ("DistributorB", "ProductY"): 60.0,
        ("DistributorC", "ProductX"): 120.0,
        ("DistributorC", "ProductY"): 40.0,
    },
    sales_ma_3={},  # Empty if using 6-month window
    sales_ma_6={
        ("DistributorA", "ProductX"): 200.0,
        ("DistributorA", "ProductY"): 150.0,
        ("DistributorB", "ProductX"): 180.0,
        ("DistributorB", "ProductY"): 120.0,
        ("DistributorC", "ProductX"): 160.0,
        ("DistributorC", "ProductY"): 100.0,
    },
    sales_mtd={
        ("DistributorA", "ProductX"): 30.0,
        ("DistributorA", "ProductY"): 25.0,
        ("DistributorB", "ProductX"): 20.0,
        ("DistributorB", "ProductY"): 15.0,
        ("DistributorC", "ProductX"): 25.0,
        ("DistributorC", "ProductY"): 20.0,
    },
    target_units={
        "ProductX": 2000.0,
        "ProductY": 1500.0
    },
    settings=settings
)
```

## Next Steps: Solving the Model

The optimization module creates an abstract LP model. To actually solve it:

1. **Export to solver format** (LP, MPS)
2. **Use a Python solver**:
   - PuLP: `pip install pulp`
   - OR-Tools: `pip install ortools`
   - scipy.optimize.linprog (for small problems)

### Example with PuLP:

```python
import pulp

# Convert your model to PuLP format
# (You'll need to write a converter or manually build the PuLP model)

prob = pulp.LpProblem("Distribution", pulp.LpMinimize)

# Add variables
# x = pulp.LpVariable.dicts("x", [(d, p) for d in distributors for p in products], lowBound=0)

# Add constraints from result.model.constraints
# ...

# Solve
prob.solve()

# Extract solution
# for (dist, prod), var in result.decision_variables.items():
#     print(f"{dist} → {prod}: {x[(dist, prod)].varValue}")
```

## Troubleshooting

### Import Errors

If you get import errors:
1. Make sure you're running from the project root
2. Check that `src` is in your Python path
3. Consider fixing import statements in the source files

### Module Structure Issues

The optimization module uses relative imports. Options:
1. Fix imports in source files to be consistent
2. Use importlib to load modules directly
3. Set up proper package structure

## Files Created for Testing

- `test_optimization.py` - Comprehensive unit tests (may need import fixes)
- `example_usage.py` - Detailed example with sample data (may need import fixes)
- `quick_test.py` - Quick validation script (may need import fixes)
- `simple_test.py` - Simple standalone test (may need import fixes)
- `README.md` - This guide
- `TESTING_GUIDE.md` - Detailed testing guide

## Recommended Approach

1. **Start with manual testing** - Create a simple script that imports and uses the modules
2. **Fix import issues** - Update the source files to have consistent imports
3. **Run unit tests** - Use the test files once imports work
4. **Integrate solver** - Connect to a solver library to get actual solutions

