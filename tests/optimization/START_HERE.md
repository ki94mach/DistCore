# How to Start Testing the Optimization Module

## Quick Answer

The optimization module has some import structure issues that need to be resolved first. Here are your options:

## Option 1: Fix Imports First (Recommended)

The source files in `src/optimization/` have inconsistent imports. Fix them to use consistent relative imports, then you can use the test files.

**Files to check:**

- `src/optimization/__init__.py` - Uses `from builder import` (should be relative)
- `src/optimization/builder.py` - Has duplicate imports
- `src/optimization/constraints/base.py` - Uses `from ..data import` (correct)

## Option 2: Test Core Concepts Manually

Create a simple script to test the core functionality:

```python
# test_manual.py in project root
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

# Test by importing and using classes directly
# You may need to import files individually to work around import issues
```

## Option 3: Use the Example Script

Once imports are fixed, run:

```bash
python tests/optimization/example_usage.py
```

This will show you:

- How to create optimization data
- How to build a model
- The structure of the resulting LP model

## What the Tests Cover

The test suite includes:

1. **LP Model Components** - Variables, expressions, constraints, objectives
2. **Data Models** - Settings and optimization data with helper methods
3. **Constraints** - Factory supply, distributor coverage, target coverage
4. **Model Builder** - Complete model construction
5. **End-to-End** - Full optimization scenario

## Next Steps

1. **Fix import issues** in the optimization module source files
2. **Run the example script** to see how it works
3. **Run unit tests** to verify functionality
4. **Integrate a solver** (PuLP, OR-Tools, etc.) to get solutions

## Files Available

- `tests/optimization/test_optimization.py` - Comprehensive unit tests
- `tests/optimization/example_usage.py` - Detailed example
- `tests/optimization/README.md` - Full testing guide
- `tests/optimization/TESTING_GUIDE.md` - Detailed testing instructions

## Quick Test Command

Once imports are fixed:

```bash
# From project root
python -m unittest tests.optimization.test_optimization -v
```

Or run the example:

```bash
python tests/optimization/example_usage.py
```
