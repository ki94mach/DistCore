# Optimization Module Testing Guide

This directory contains tests for the `src/optimization/` module.

## Quick Start

### Option 1: Run the Example Script (Recommended for First-Time Testing)

The easiest way to start testing is to run the example script that demonstrates the optimization module:

```bash
# From project root
python tests/optimization/example_usage.py
```

This script will:
- Create sample optimization data
- Build a model with all constraints
- Display a detailed summary of the model structure
- Show constraint details

### Option 2: Run Unit Tests

Due to import structure in the optimization module, run tests from the project root:

```bash
# From project root
python -m unittest discover -s tests/optimization -p "test_*.py" -v
```

Or run a specific test class:

```bash
python -m unittest tests.optimization.test_optimization.TestLPModel -v
```

## Test Structure

```
tests/optimization/
├── __init__.py
├── test_optimization.py      # Comprehensive unit tests
├── example_usage.py          # Example script with sample data
└── README.md                 # This file
```

## What's Tested

### `test_optimization.py` includes:

1. **LP Model Primitives** (`TestLPModel`)
   - Variable creation and bounds
   - Linear expression building
   - Constraint management
   - Objective function setting

2. **Data Models** (`TestOptimizationData`)
   - OptimizationSettings
   - OptimizationData creation
   - Helper methods (inventory, sales, coverage demand, etc.)

3. **Constraints** (`TestConstraints`)
   - FactorySupplyConstraint (hard constraint)
   - DemandCoverageConstraint (soft constraint)
   - ProductTargetUnitsConstraint (soft constraint)

4. **Model Builder** (`TestModelBuilder`)
   - Decision variable creation
   - Complete model building
   - Objective function construction

5. **End-to-End** (`TestEndToEnd`)
   - Complete optimization scenario
   - Realistic data setup
   - Model verification

## Creating Your Own Test Data

Here's a template for creating test data:

```python
from src.optimization.data import OptimizationData, OptimizationSettings

settings = OptimizationSettings(
    coverage_ratio=1.5,           # Distributor coverage: 1.5x demand
    target_coverage_ratio=1.5,   # Target units coverage: 1.5x target
    sales_window=6,               # Use 6-month moving average
    weight_demand=1.0,         # Weight for demand coverage slack
    weight_target_units=2.0       # Weight for target units slack
)

data = OptimizationData(
    distributors=["Dist1", "Dist2"],
    products=["Prod1", "Prod2"],
    factory_inventory={"Prod1": 1000.0, "Prod2": 800.0},
    distributor_inventory={
        ("Dist1", "Prod1"): 100.0,
        ("Dist2", "Prod1"): 80.0,
        # ... more entries
    },
    sales_ma_3={},  # Empty if using 6-month window
    sales_ma_6={
        ("Dist1", "Prod1"): 200.0,
        # ... more entries
    },
    sales_mtd={
        ("Dist1", "Prod1"): 30.0,
        # ... more entries
    },
    target_units={"Prod1": 2000.0, "Prod2": 1500.0},
    settings=settings
)
```

## Building and Inspecting Models

```python
from src.optimization.builder import ModelBuilder
from src.optimization.constraints.factory_supply import FactorySupplyConstraint
from src.optimization.constraints.demand_coverage import DemandCoverageConstraint
from src.optimization.constraints.target_coverage import ProductTargetUnitsConstraint

# Create constraints
constraints = [
    FactorySupplyConstraint(),
    DemandCoverageConstraint(),
    ProductTargetUnitsConstraint()
]

# Build model
builder = ModelBuilder(constraints)
result = builder.build(data)

# Inspect model
print(f"Decision variables: {len(result.decision_variables)}")
print(f"Total variables: {len(result.model.variables)}")
print(f"Constraints: {len(result.model.constraints)}")
print(f"Objective: {result.model.objective.sense}")
```

## Next Steps: Solving the Model

The optimization module creates an abstract LP model. To actually solve it, you need to:

1. **Export to a solver format** (LP, MPS, etc.)
2. **Use a Python solver library**:
   - [PuLP](https://github.com/coin-or/pulp) - Popular, easy to use
   - [OR-Tools](https://developers.google.com/optimization) - Google's optimization tools
   - [scipy.optimize.linprog](https://docs.scipy.org/doc/scipy/reference/generated/scipy.optimize.linprog.html) - For small problems

### Example with PuLP (if installed):

```python
import pulp

# Convert model to PuLP format
prob = pulp.LpProblem("Distribution", pulp.LpMinimize)

# Add variables, constraints, objective from result.model
# ... (conversion code needed)

# Solve
prob.solve()

# Extract solution
for (dist, prod), var in result.decision_variables.items():
    print(f"{dist} → {prod}: {var.value()}")
```

## Troubleshooting

### Import Errors

If you encounter import errors, make sure you're running from the project root:

```bash
cd /path/to/DistCore
python tests/optimization/example_usage.py
```

### Module Structure Issues

The optimization module uses relative imports. If tests fail, try running the example script first, which uses a more direct import approach.

## Manual Testing Checklist

- [ ] Run `example_usage.py` successfully
- [ ] Verify model structure (variables, constraints, objective)
- [ ] Check constraint calculations match expected values
- [ ] Test with different settings (coverage_ratio, sales_window)
- [ ] Test edge cases (zero inventory, negative demand, etc.)
- [ ] Verify hard constraints (factory supply) are enforced
- [ ] Verify soft constraints (coverage) have slack variables

