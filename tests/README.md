# Testing Guide

This directory contains tests for the DistCore orchestrator pipelines.

## Test Structure

```
tests/
├── pipelines/
│   ├── test_factory_inventory.py           # Unit tests (mocked)
│   └── test_factory_inventory_integration.py  # Integration tests (real DB)
```

## Running Tests

### Unit Tests (No Database Required)

```bash
# Run all unit tests
python -m pytest tests/pipelines/test_factory_inventory.py -v

# Run specific test
python -m pytest tests/pipelines/test_factory_inventory.py::TestFactoryInventoryPipeline::test_load_stage -v

# Run with unittest
python -m unittest tests.pipelines.test_factory_inventory
```

### Integration Tests (Requires Database)

```bash
# Make sure your database config is set up in:
# src/orchestrator/config/db.yml

# Run integration tests
python -m pytest tests/pipelines/test_factory_inventory_integration.py -v

# Or with unittest
python -m unittest tests.pipelines.test_factory_inventory_integration
```

## Test Types

### Unit Tests
- Mock all database interactions
- Fast execution
- No database required
- Test method logic and parameter passing

### Integration Tests
- Use real database connections
- Test actual SQL execution
- Verify end-to-end pipeline flow
- Marked with `@unittest.skip` by default - uncomment to run

## Manual Testing

You can also test the pipeline manually:

```python
from datetime import date
from orchestrator.pipelines.factory_inventory import FactoryInventoryPipeline

# Create pipeline instance
pipeline = FactoryInventoryPipeline(
    batch_id=123,
    snapshot_date=date(2024, 1, 15)
)

# Run full pipeline
pipeline.run()

# Or test individual stages
pipeline.load_stage()
pipeline.validate()
pipeline.publish()
```

## Test Data Setup

For integration tests, ensure:
1. Database connection is configured correctly
2. Test stored procedures exist in the database
3. Test batch IDs don't conflict with production data
4. Consider using a separate test database

