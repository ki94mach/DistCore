"""Comprehensive tests for the optimization module."""

import unittest
import sys
from pathlib import Path

# Add project root to Python path
_project_root = Path(__file__).resolve().parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

# Import using direct file imports to work around module import issues
import importlib.util

_src_opt = _project_root / "src" / "optimization"

# Load lp module
lp_path = _src_opt / "lp.py"
lp_spec = importlib.util.spec_from_file_location("lp", lp_path)
lp = importlib.util.module_from_spec(lp_spec)
sys.modules["lp"] = lp
lp_spec.loader.exec_module(lp)

# Load data module  
data_path = _src_opt / "data.py"
data_spec = importlib.util.spec_from_file_location("data", data_path)
data = importlib.util.module_from_spec(data_spec)
sys.modules["data"] = data
data_spec.loader.exec_module(data)

# Load base constraint module first (needed by others)
base_path = _src_opt / "constraints" / "base.py"
base_spec = importlib.util.spec_from_file_location("base", base_path)
base = importlib.util.module_from_spec(base_spec)
sys.modules["base"] = base
# Inject dependencies
base.OptimizationData = data.OptimizationData
base.Model = lp.Model
base.Variable = lp.Variable
base_spec.loader.exec_module(base)

# Load constraint modules
factory_supply_path = _src_opt / "constraints" / "factory_supply.py"
factory_supply_spec = importlib.util.spec_from_file_location("factory_supply", factory_supply_path)
factory_supply = importlib.util.module_from_spec(factory_supply_spec)
sys.modules["factory_supply"] = factory_supply
factory_supply.OptimizationData = data.OptimizationData
factory_supply.Model = lp.Model
factory_supply.Variable = lp.Variable
factory_supply.linear_sum = lp.linear_sum
factory_supply.Constraint = base.Constraint
factory_supply.ConstraintResult = base.ConstraintResult
factory_supply_spec.loader.exec_module(factory_supply)

distributor_coverage_path = _src_opt / "constraints" / "distributor_coverage.py"
distributor_coverage_spec = importlib.util.spec_from_file_location("distributor_coverage", distributor_coverage_path)
distributor_coverage = importlib.util.module_from_spec(distributor_coverage_spec)
sys.modules["distributor_coverage"] = distributor_coverage
distributor_coverage.OptimizationData = data.OptimizationData
distributor_coverage.Model = lp.Model
distributor_coverage.Variable = lp.Variable
distributor_coverage.linear_sum = lp.linear_sum
distributor_coverage.Constraint = base.Constraint
distributor_coverage.ConstraintResult = base.ConstraintResult
distributor_coverage_spec.loader.exec_module(distributor_coverage)

target_coverage_path = _src_opt / "constraints" / "target_coverage.py"
target_coverage_spec = importlib.util.spec_from_file_location("target_coverage", target_coverage_path)
target_coverage = importlib.util.module_from_spec(target_coverage_spec)
sys.modules["target_coverage"] = target_coverage
target_coverage.OptimizationData = data.OptimizationData
target_coverage.Model = lp.Model
target_coverage.Variable = lp.Variable
target_coverage.linear_sum = lp.linear_sum
target_coverage.Constraint = base.Constraint
target_coverage.ConstraintResult = base.ConstraintResult
target_coverage_spec.loader.exec_module(target_coverage)

# Load builder module
builder_path = _src_opt / "builder.py"
builder_spec = importlib.util.spec_from_file_location("builder", builder_path)
builder = importlib.util.module_from_spec(builder_spec)
sys.modules["builder"] = builder
builder.Constraint = base.Constraint
builder.ConstraintResult = base.ConstraintResult
builder.OptimizationData = data.OptimizationData
builder.LinearExpression = lp.LinearExpression
builder.Model = lp.Model
builder.Variable = lp.Variable
builder.linear_sum = lp.linear_sum
builder_spec.loader.exec_module(builder)

# Import classes for use in tests
Variable = lp.Variable
LinearExpression = lp.LinearExpression
Constraint = lp.Constraint
Model = lp.Model
Objective = lp.Objective
linear_sum = lp.linear_sum
OptimizationData = data.OptimizationData
OptimizationSettings = data.OptimizationSettings
ModelBuilder = builder.ModelBuilder
ModelBuildResult = builder.ModelBuildResult
FactorySupplyConstraint = factory_supply.FactorySupplyConstraint
DistributorCoverageConstraint = distributor_coverage.DistributorCoverageConstraint
ProductTargetUnitsConstraint = target_coverage.ProductTargetUnitsConstraint


class TestLPModel(unittest.TestCase):
    """Test LP model primitives."""

    def test_variable_creation(self):
        """Test variable creation with bounds."""
        var1 = Variable(name="x1", low=0.0, up=100.0)
        self.assertEqual(var1.name, "x1")
        self.assertEqual(var1.low, 0.0)
        self.assertEqual(var1.up, 100.0)

        var2 = Variable(name="x2", low=0.0)
        self.assertIsNone(var2.up)

    def test_linear_expression(self):
        """Test linear expression building."""
        var1 = Variable(name="x1")
        var2 = Variable(name="x2")
        
        expr = LinearExpression(constant=5.0)
        expr.add_term(var1, 2.0)
        expr.add_term(var2, 3.0)
        expr.add_term(var1, 1.0)  # Should accumulate
        
        self.assertEqual(expr.constant, 5.0)
        self.assertEqual(expr.coefficients[var1], 3.0)  # 2.0 + 1.0
        self.assertEqual(expr.coefficients[var2], 3.0)

    def test_linear_sum_helper(self):
        """Test linear_sum helper function."""
        var1 = Variable(name="x1")
        var2 = Variable(name="x2")
        
        expr = linear_sum([(var1, 2.0), (var2, 3.0)], constant=1.0)
        
        self.assertEqual(expr.constant, 1.0)
        self.assertEqual(expr.coefficients[var1], 2.0)
        self.assertEqual(expr.coefficients[var2], 3.0)

    def test_model_variable_management(self):
        """Test model variable management."""
        model = Model()
        var1 = model.add_variable("x1", low=0.0, up=10.0)
        var2 = model.add_variable("x2", low=5.0)
        
        self.assertEqual(len(model.variables), 2)
        self.assertEqual(var1.name, "x1")
        self.assertEqual(var2.low, 5.0)

    def test_model_constraint_management(self):
        """Test model constraint management."""
        model = Model()
        var1 = model.add_variable("x1")
        var2 = model.add_variable("x2")
        
        expr = linear_sum([(var1, 1.0), (var2, 2.0)], constant=0.0)
        model.add_constraint(expr, "<=", 10.0, "c1")
        
        self.assertEqual(len(model.constraints), 1)
        self.assertEqual(model.constraints[0].name, "c1")
        self.assertEqual(model.constraints[0].rhs, 10.0)
        self.assertEqual(model.constraints[0].sense, "<=")

    def test_model_constraint_sense_validation(self):
        """Test constraint sense validation."""
        model = Model()
        var1 = model.add_variable("x1")
        expr = linear_sum([(var1, 1.0)])
        
        # Valid senses
        model.add_constraint(expr, "<=", 10.0, "c1")
        model.add_constraint(expr, ">=", 5.0, "c2")
        model.add_constraint(expr, "=", 7.0, "c3")
        
        # Invalid sense
        with self.assertRaises(ValueError):
            model.add_constraint(expr, "!=", 10.0, "c4")

    def test_model_objective(self):
        """Test objective setting."""
        model = Model()
        var1 = model.add_variable("x1")
        var2 = model.add_variable("x2")
        
        expr = linear_sum([(var1, 1.0), (var2, 2.0)])
        model.set_objective(expr, sense="min")
        
        self.assertIsNotNone(model.objective)
        self.assertEqual(model.objective.sense, "min")
        
        model.set_objective(expr, sense="max")
        self.assertEqual(model.objective.sense, "max")
        
        with self.assertRaises(ValueError):
            model.set_objective(expr, sense="optimize")


class TestOptimizationData(unittest.TestCase):
    """Test OptimizationData and OptimizationSettings."""

    def test_optimization_settings(self):
        """Test settings initialization."""
        settings = OptimizationSettings(
            coverage_ratio=1.5,
            sales_window=6,
            weight_coverage=1.0,
            weight_target_units=2.0
        )
        self.assertEqual(settings.coverage_ratio, 1.5)
        self.assertEqual(settings.sales_window, 6)
        self.assertEqual(settings.weight_coverage, 1.0)
        self.assertEqual(settings.weight_target_units, 2.0)

    def test_optimization_data_creation(self):
        """Test OptimizationData creation."""
        settings = OptimizationSettings()
        data = OptimizationData(
            distributors=["D1", "D2"],
            products=["P1", "P2"],
            factory_inventory={"P1": 100.0, "P2": 200.0},
            distributor_inventory={("D1", "P1"): 10.0, ("D2", "P1"): 20.0},
            sales_ma_3={("D1", "P1"): 50.0},
            sales_ma_6={("D1", "P1"): 60.0},
            sales_mtd={("D1", "P1"): 5.0},
            target_units={"P1": 500.0},
            settings=settings
        )
        
        self.assertEqual(len(data.distributors), 2)
        self.assertEqual(len(data.products), 2)

    def test_inventory_methods(self):
        """Test inventory helper methods."""
        settings = OptimizationSettings()
        data = OptimizationData(
            distributors=["D1"],
            products=["P1"],
            factory_inventory={"P1": 100.0},
            distributor_inventory={("D1", "P1"): 10.0},
            sales_ma_3={},
            sales_ma_6={},
            sales_mtd={},
            target_units={},
            settings=settings
        )
        
        self.assertEqual(data.inventory("D1", "P1"), 10.0)
        self.assertEqual(data.inventory("D1", "P2"), 0.0)  # Missing
        self.assertEqual(data.factory_supply("P1"), 100.0)
        self.assertEqual(data.factory_supply("P2"), 0.0)  # Missing

    def test_sales_moving_average(self):
        """Test sales moving average selection."""
        settings_3 = OptimizationSettings(sales_window=3)
        settings_6 = OptimizationSettings(sales_window=6)
        
        data_3 = OptimizationData(
            distributors=["D1"],
            products=["P1"],
            factory_inventory={},
            distributor_inventory={},
            sales_ma_3={("D1", "P1"): 50.0},
            sales_ma_6={("D1", "P1"): 60.0},
            sales_mtd={},
            target_units={},
            settings=settings_3
        )
        
        data_6 = OptimizationData(
            distributors=["D1"],
            products=["P1"],
            factory_inventory={},
            distributor_inventory={},
            sales_ma_3={("D1", "P1"): 50.0},
            sales_ma_6={("D1", "P1"): 60.0},
            sales_mtd={},
            target_units={},
            settings=settings_6
        )
        
        self.assertEqual(data_3.sales_moving_average("D1", "P1"), 50.0)
        self.assertEqual(data_6.sales_moving_average("D1", "P1"), 60.0)

    def test_coverage_demand(self):
        """Test coverage demand calculation."""
        settings = OptimizationSettings(sales_window=6)
        data = OptimizationData(
            distributors=["D1"],
            products=["P1"],
            factory_inventory={},
            distributor_inventory={},
            sales_ma_3={},
            sales_ma_6={("D1", "P1"): 100.0},
            sales_mtd={("D1", "P1"): 30.0},
            target_units={},
            settings=settings
        )
        
        # demand = max(0, 100 - 30) = 70
        self.assertEqual(data.coverage_demand("D1", "P1"), 70.0)
        
        # Test negative demand (should be 0)
        data_neg = OptimizationData(
            distributors=["D1"],
            products=["P1"],
            factory_inventory={},
            distributor_inventory={},
            sales_ma_3={},
            sales_ma_6={("D1", "P1"): 20.0},
            sales_mtd={("D1", "P1"): 30.0},
            target_units={},
            settings=settings
        )
        self.assertEqual(data_neg.coverage_demand("D1", "P1"), 0.0)

    def test_remaining_target_units(self):
        """Test remaining target units calculation."""
        settings = OptimizationSettings()
        data = OptimizationData(
            distributors=["D1", "D2"],
            products=["P1"],
            factory_inventory={},
            distributor_inventory={},
            sales_ma_3={},
            sales_ma_6={},
            sales_mtd={("D1", "P1"): 100.0, ("D2", "P1"): 50.0},
            target_units={"P1": 500.0},
            settings=settings
        )
        
        # remaining = max(0, 500 - 150) = 350
        self.assertEqual(data.remaining_target_units("P1"), 350.0)
        
        # Test when target is exceeded
        data_exceeded = OptimizationData(
            distributors=["D1"],
            products=["P1"],
            factory_inventory={},
            distributor_inventory={},
            sales_ma_3={},
            sales_ma_6={},
            sales_mtd={("D1", "P1"): 600.0},
            target_units={"P1": 500.0},
            settings=settings
        )
        self.assertEqual(data_exceeded.remaining_target_units("P1"), 0.0)


class TestConstraints(unittest.TestCase):
    """Test individual constraint implementations."""

    def setUp(self):
        """Set up test data."""
        self.settings = OptimizationSettings(
            coverage_ratio=1.5,
            sales_window=6,
            weight_coverage=1.0,
            weight_target_units=1.0
        )
        self.data = OptimizationData(
            distributors=["D1", "D2"],
            products=["P1"],
            factory_inventory={"P1": 100.0},
            distributor_inventory={("D1", "P1"): 10.0, ("D2", "P1"): 20.0},
            sales_ma_3={},
            sales_ma_6={("D1", "P1"): 50.0, ("D2", "P1"): 30.0},
            sales_mtd={("D1", "P1"): 5.0, ("D2", "P1"): 10.0},
            target_units={"P1": 200.0},
            settings=self.settings
        )

    def test_factory_supply_constraint(self):
        """Test factory supply constraint (hard constraint)."""
        model = Model()
        x = {
            ("D1", "P1"): model.add_variable("x_D1_P1"),
            ("D2", "P1"): model.add_variable("x_D2_P1")
        }
        
        constraint = FactorySupplyConstraint()
        result = constraint.apply(model, self.data, x)
        
        # Should have one constraint for product P1
        self.assertEqual(len(model.constraints), 1)
        self.assertEqual(model.constraints[0].name, "factory_supply_P1")
        self.assertEqual(model.constraints[0].sense, "<=")
        self.assertEqual(model.constraints[0].rhs, 100.0)
        
        # Hard constraint should not add slack variables
        self.assertEqual(len(result.slack_variables), 0)
        self.assertEqual(len(result.objective_terms), 0)

    def test_distributor_coverage_constraint(self):
        """Test distributor coverage constraint (soft constraint)."""
        model = Model()
        x = {
            ("D1", "P1"): model.add_variable("x_D1_P1"),
            ("D2", "P1"): model.add_variable("x_D2_P1")
        }
        
        constraint = DistributorCoverageConstraint()
        result = constraint.apply(model, self.data, x)
        
        # Should have 2 constraints (one per distributor)
        self.assertEqual(len(model.constraints), 2)
        
        # Check D1 constraint
        # demand = max(0, 50 - 5) = 45
        # target = 1.5 * 45 = 67.5
        # constraint: x_D1_P1 + 10 + slack >= 67.5
        d1_constraint = next(c for c in model.constraints if "D1" in c.name)
        self.assertEqual(d1_constraint.sense, ">=")
        self.assertEqual(d1_constraint.rhs, 67.5)
        
        # Should have 2 slack variables
        self.assertEqual(len(result.slack_variables), 2)
        self.assertEqual(len(result.objective_terms), 2)
        # Check weights
        self.assertEqual(result.objective_terms[0][1], 1.0)

    def test_target_coverage_constraint(self):
        """Test target coverage constraint (soft constraint)."""
        model = Model()
        x = {
            ("D1", "P1"): model.add_variable("x_D1_P1"),
            ("D2", "P1"): model.add_variable("x_D2_P1")
        }
        
        constraint = ProductTargetUnitsConstraint()
        result = constraint.apply(model, self.data, x)
        
        # Should have 1 constraint for product P1
        self.assertEqual(len(model.constraints), 1)
        self.assertEqual(model.constraints[0].name, "target_units_P1")
        
        # remaining_target = max(0, 200 - 15) = 185
        # target = 1.5 * 185 = 277.5
        # total_inventory = 10 + 20 = 30
        # constraint: x_D1_P1 + x_D2_P1 + 30 + slack >= 277.5
        self.assertEqual(model.constraints[0].rhs, 277.5)
        self.assertEqual(model.constraints[0].sense, ">=")
        
        # Should have 1 slack variable
        self.assertEqual(len(result.slack_variables), 1)
        self.assertEqual(len(result.objective_terms), 1)


class TestModelBuilder(unittest.TestCase):
    """Test ModelBuilder integration."""

    def setUp(self):
        """Set up test data."""
        self.settings = OptimizationSettings(
            coverage_ratio=1.5,
            sales_window=6,
            weight_coverage=1.0,
            weight_target_units=1.0
        )
        self.data = OptimizationData(
            distributors=["D1", "D2"],
            products=["P1", "P2"],
            factory_inventory={"P1": 100.0, "P2": 200.0},
            distributor_inventory={
                ("D1", "P1"): 10.0,
                ("D2", "P1"): 20.0,
                ("D1", "P2"): 15.0,
                ("D2", "P2"): 25.0
            },
            sales_ma_3={},
            sales_ma_6={
                ("D1", "P1"): 50.0,
                ("D2", "P1"): 30.0,
                ("D1", "P2"): 40.0,
                ("D2", "P2"): 60.0
            },
            sales_mtd={
                ("D1", "P1"): 5.0,
                ("D2", "P1"): 10.0,
                ("D1", "P2"): 8.0,
                ("D2", "P2"): 12.0
            },
            target_units={"P1": 200.0, "P2": 300.0},
            settings=self.settings
        )

    def test_model_builder_creation(self):
        """Test ModelBuilder initialization."""
        constraints = [
            FactorySupplyConstraint(),
            DistributorCoverageConstraint(),
            ProductTargetUnitsConstraint()
        ]
        builder = ModelBuilder(constraints)
        self.assertEqual(len(builder.constraints), 3)

    def test_model_builder_decision_variables(self):
        """Test decision variable creation."""
        constraints = [FactorySupplyConstraint()]
        builder = ModelBuilder(constraints)
        result = builder.build(self.data)
        
        # Should have 4 decision variables (2 distributors × 2 products)
        self.assertEqual(len(result.decision_variables), 4)
        self.assertIn(("D1", "P1"), result.decision_variables)
        self.assertIn(("D2", "P2"), result.decision_variables)

    def test_model_builder_complete_model(self):
        """Test complete model building with all constraints."""
        constraints = [
            FactorySupplyConstraint(),
            DistributorCoverageConstraint(),
            ProductTargetUnitsConstraint()
        ]
        builder = ModelBuilder(constraints)
        result = builder.build(self.data)
        
        model = result.model
        
        # Check variables: 4 decision + slack variables
        # 4 decision variables
        # 4 slack for distributor coverage (2 dist × 2 prod)
        # 2 slack for target coverage (2 products)
        # Total: 4 + 4 + 2 = 10
        self.assertEqual(len(model.variables), 10)
        
        # Check constraints:
        # 2 factory supply (one per product)
        # 4 distributor coverage (2 dist × 2 prod)
        # 2 target coverage (one per product)
        # Total: 2 + 4 + 2 = 8
        self.assertEqual(len(model.constraints), 8)
        
        # Check objective exists
        self.assertIsNotNone(model.objective)
        self.assertEqual(model.objective.sense, "min")
        
        # Check slack variables collected
        self.assertEqual(len(result.slack_variables), 6)  # 4 + 2

    def test_model_builder_objective_terms(self):
        """Test objective function construction."""
        constraints = [
            DistributorCoverageConstraint(),
            ProductTargetUnitsConstraint()
        ]
        builder = ModelBuilder(constraints)
        result = builder.build(self.data)
        
        # Objective should minimize weighted slack
        objective = result.model.objective
        self.assertIsNotNone(objective)
        
        # Should have 6 terms (4 coverage + 2 target)
        self.assertEqual(len(objective.expression.coefficients), 6)


class TestEndToEnd(unittest.TestCase):
    """End-to-end test with realistic scenario."""

    def test_simple_optimization_scenario(self):
        """Test a simple optimization scenario."""
        # Create realistic test data
        settings = OptimizationSettings(
            coverage_ratio=1.5,
            sales_window=6,
            weight_coverage=1.0,
            weight_target_units=2.0
        )
        
        data = OptimizationData(
            distributors=["DistA", "DistB"],
            products=["ProductX"],
            factory_inventory={"ProductX": 500.0},
            distributor_inventory={
                ("DistA", "ProductX"): 50.0,
                ("DistB", "ProductX"): 30.0
            },
            sales_ma_3={},
            sales_ma_6={
                ("DistA", "ProductX"): 200.0,
                ("DistB", "ProductX"): 150.0
            },
            sales_mtd={
                ("DistA", "ProductX"): 40.0,
                ("DistB", "ProductX"): 30.0
            },
            target_units={"ProductX": 1000.0},
            settings=settings
        )
        
        # Build model
        constraints = [
            FactorySupplyConstraint(),
            DistributorCoverageConstraint(),
            ProductTargetUnitsConstraint()
        ]
        builder = ModelBuilder(constraints)
        result = builder.build(data)
        
        # Verify model structure
        self.assertIsNotNone(result.model)
        self.assertEqual(len(result.decision_variables), 2)
        self.assertEqual(len(result.model.constraints), 4)  # 1 factory + 2 coverage + 1 target
        
        # Verify factory constraint
        factory_constraint = next(c for c in result.model.constraints if "factory_supply" in c.name)
        self.assertEqual(factory_constraint.rhs, 500.0)
        
        # Verify coverage constraints
        # DistA: demand = max(0, 200-40) = 160, target = 1.5 * 160 = 240
        dista_constraint = next(c for c in result.model.constraints if "DistA" in c.name and "coverage" in c.name)
        self.assertEqual(dista_constraint.rhs, 240.0)
        
        # Verify objective
        self.assertIsNotNone(result.model.objective)
        self.assertEqual(result.model.objective.sense, "min")


if __name__ == '__main__':
    unittest.main()

