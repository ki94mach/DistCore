"""Example script showing how to use the optimization module.

This script demonstrates how to:
1. Create optimization data
2. Build a model with constraints
3. Inspect the resulting LP model

Note: This doesn't solve the model (requires an external solver).
To actually solve, you would need to export the model to a solver format
or use a Python solver library like PuLP, OR-Tools, or scipy.optimize.
"""

import sys
from pathlib import Path

# Add project root to Python path
_project_root = Path(__file__).resolve().parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

# Import directly from source files
_optimization_path = Path(__file__).resolve().parent.parent / "src" / "optimization"
if str(_optimization_path.parent) not in sys.path:
    sys.path.insert(0, str(_optimization_path.parent))

from src.optimization.data import OptimizationData, OptimizationSettings
from src.optimization.builder import ModelBuilder
from src.optimization.constraints.factory_supply import FactorySupplyConstraint
from src.optimization.constraints.demand_coverage import DemandCoverageConstraint
from src.optimization.constraints.target_coverage import ProductTargetUnitsConstraint


def create_sample_data():
    """Create sample optimization data."""
    settings = OptimizationSettings(
        coverage_ratio=1.5,           # Distributor coverage: 1.5x demand
        target_coverage_ratio=1.5,   # Target units coverage: 1.5x target
        sales_window=6,               # Use 6-month moving average
        weight_coverage=1.0,         # Weight for coverage slack
        weight_target_units=2.0       # Weight for target units slack (higher priority)
    )
    
    data = OptimizationData(
        distributors=["DistributorA", "DistributorB", "DistributorC"],
        products=["ProductX", "ProductY"],
        
        # Factory inventory (available to ship)
        factory_inventory={
            "ProductX": 1000.0,
            "ProductY": 800.0
        },
        
        # Current distributor inventory
        distributor_inventory={
            ("DistributorA", "ProductX"): 100.0,
            ("DistributorA", "ProductY"): 50.0,
            ("DistributorB", "ProductX"): 80.0,
            ("DistributorB", "ProductY"): 60.0,
            ("DistributorC", "ProductX"): 120.0,
            ("DistributorC", "ProductY"): 40.0,
        },
        
        # 6-month moving average sales
        sales_ma_3={},
        sales_ma_6={
            ("DistributorA", "ProductX"): 200.0,
            ("DistributorA", "ProductY"): 150.0,
            ("DistributorB", "ProductX"): 180.0,
            ("DistributorB", "ProductY"): 120.0,
            ("DistributorC", "ProductX"): 160.0,
            ("DistributorC", "ProductY"): 100.0,
        },
        
        # Month-to-date sales
        sales_mtd={
            ("DistributorA", "ProductX"): 30.0,
            ("DistributorA", "ProductY"): 25.0,
            ("DistributorB", "ProductX"): 20.0,
            ("DistributorB", "ProductY"): 15.0,
            ("DistributorC", "ProductX"): 25.0,
            ("DistributorC", "ProductY"): 20.0,
        },
        
        # Product-level sales targets
        target_units={
            "ProductX": 2000.0,
            "ProductY": 1500.0
        },
        
        settings=settings
    )
    
    return data


def print_model_summary(result):
    """Print a summary of the built model."""
    model = result.model
    
    print("\n" + "="*60)
    print("OPTIMIZATION MODEL SUMMARY")
    print("="*60)
    
    print(f"\nDecision Variables: {len(result.decision_variables)}")
    for (dist, prod), var in result.decision_variables.items():
        print(f"  {var.name}: {dist} → {prod}")
    
    print(f"\nTotal Variables: {len(model.variables)}")
    print(f"  - Decision variables: {len(result.decision_variables)}")
    print(f"  - Slack variables: {len(result.slack_variables)}")
    
    print(f"\nConstraints: {len(model.constraints)}")
    constraint_types = {}
    for constraint in model.constraints:
        constraint_type = constraint.name.split('_')[0]
        constraint_types[constraint_type] = constraint_types.get(constraint_type, 0) + 1
    
    for ctype, count in constraint_types.items():
        print(f"  - {ctype}: {count}")
    
    print(f"\nObjective: {model.objective.sense.upper()}")
    if model.objective:
        print(f"  Objective terms: {len(model.objective.expression.coefficients)}")
    
    print("\n" + "="*60)


def print_constraint_details(result, data):
    """Print detailed constraint information."""
    print("\n" + "="*60)
    print("CONSTRAINT DETAILS")
    print("="*60)
    
    # Factory supply constraints
    print("\n1. FACTORY SUPPLY CONSTRAINTS (Hard)")
    print("-" * 60)
    for constraint in result.model.constraints:
        if "factory_supply" in constraint.name:
            product = constraint.name.split("_")[-1]
            print(f"  {constraint.name}:")
            print(f"    Σ shipments[{product}] ≤ {constraint.rhs}")
            print(f"    Available factory inventory: {data.factory_supply(product)}")
    
    # Demand coverage constraints
    print("\n2. DEMAND COVERAGE CONSTRAINTS (Soft)")
    print("-" * 60)
    for constraint in result.model.constraints:
        if "demand_coverage_" in constraint.name and "target_units" not in constraint.name:
            parts = constraint.name.split("_")
            if len(parts) >= 4:  # demand_coverage_{distributor}_{product}
                distributor = parts[2]
                product = parts[3]
                demand = data.coverage_demand(distributor, product)
                inventory = data.inventory(distributor, product)
                target = constraint.rhs
                print(f"  {constraint.name}:")
                print(f"    Distributor: {distributor}, Product: {product}")
                print(f"    Demand: {demand:.2f} (MA: {data.sales_moving_average(distributor, product):.2f}, MTD: {data.sales_month_to_date(distributor, product):.2f})")
                print(f"    Current inventory: {inventory:.2f}")
                print(f"    Target coverage: {target:.2f} (ratio × demand)")
                print(f"    Constraint: shipment + {inventory:.2f} + slack ≥ {target:.2f}")
    
    # Target coverage constraints
    print("\n3. TARGET COVERAGE CONSTRAINTS (Soft)")
    print("-" * 60)
    for constraint in result.model.constraints:
        if "target_units" in constraint.name:
            product = constraint.name.split("_")[-1]
            remaining = data.remaining_target_units(product)
            total_inventory = sum(
                data.inventory(dist, product) 
                for dist in data.distributors
            )
            target = constraint.rhs
            print(f"  {constraint.name}:")
            print(f"    Product: {product}")
            print(f"    Remaining target: {remaining:.2f}")
            print(f"    Total distributor inventory: {total_inventory:.2f}")
            print(f"    Target coverage: {target:.2f} (ratio × remaining_target)")
            print(f"    Constraint: Σ shipments + {total_inventory:.2f} + slack ≥ {target:.2f}")


def main():
    """Main example function."""
    print("Optimization Module Example")
    print("="*60)
    
    # Create sample data
    print("\n1. Creating sample optimization data...")
    data = create_sample_data()
    print(f"   Distributors: {data.distributors}")
    print(f"   Products: {data.products}")
    print(f"   Settings: coverage_ratio={data.settings.coverage_ratio}, target_coverage_ratio={data.settings.target_coverage_ratio}, "
          f"sales_window={data.settings.sales_window}")
    
    # Create constraints
    print("\n2. Setting up constraints...")
    constraints = [
        FactorySupplyConstraint(),      # Hard: factory capacity
        DemandCoverageConstraint(), # Soft: demand coverage
        ProductTargetUnitsConstraint()   # Soft: product targets
    ]
    print(f"   Constraints: {[c.name for c in constraints]}")
    
    # Build model
    print("\n3. Building optimization model...")
    builder = ModelBuilder(constraints)
    result = builder.build(data)
    print("   Model built successfully!")
    
    # Print summaries
    print_model_summary(result)
    print_constraint_details(result, data)
    
    print("\n" + "="*60)
    print("NEXT STEPS:")
    print("="*60)
    print("To solve this model, you would need to:")
    print("1. Export the model to a solver format (e.g., LP format, MPS format)")
    print("2. Use a Python solver library like:")
    print("   - PuLP (https://github.com/coin-or/pulp)")
    print("   - OR-Tools (https://developers.google.com/optimization)")
    print("   - scipy.optimize.linprog (for small problems)")
    print("3. Extract the solution values for decision variables")
    print("4. Interpret the results as shipment quantities")
    print("="*60)


if __name__ == '__main__':
    main()

