# Procedure Catalog System

## Overview

The Procedure Catalog system provides a centralized way to store, manage, and track stored procedures in the database and provides comprehensive metadata management for all stored procedures.

## Architecture

### Tables

1. **`[Data].[ctl_ProcedureCatalog]`** - Main catalog table storing procedure metadata
   - `procedure_name` (PK) - Full procedure name (e.g., `[Data].[etl_usp_run_factory_inventory_snapshot_pipeline]`)
   - `schema_name` - Schema where procedure resides
   - `procedure_category` - Category (CTL, ETL, DQ, OPT, etc.)
   - `description` - Short description
   - `purpose` - Detailed purpose/usage documentation
   - `is_enabled` - Enable/disable flag
   - `version` - Version tracking
   - `created_at`, `updated_at` - Timestamps
   - `created_by` - Creator identifier
   - `notes` - Additional notes and dependencies

2. **`[Data].[ctl_ProcedureParameter]`** - Parameter definitions for procedures
   - `parameter_id` (PK) - Auto-increment ID
   - `procedure_name` (FK) - Links to ProcedureCatalog
   - `parameter_name` - Parameter name (without @ prefix)
   - `parameter_type` - INPUT, OUTPUT, or INPUT_OUTPUT
   - `sql_data_type` - SQL data type (e.g., DATE, NVARCHAR(100))
   - `is_required` - Whether parameter is required
   - `default_value` - Default value if any
   - `description` - Parameter description
   - `ordinal_position` - Order in procedure signature

3. **`[Data].[ctl_ProcedureExecution]`** - Execution history tracking (optional)
   - `execution_id` (PK) - Auto-increment ID
   - `procedure_name` (FK) - Links to ProcedureCatalog
   - `batch_id` (FK) - Optional link to BatchRun
   - `started_at`, `finished_at` - Execution timestamps
   - `duration_ms` - Execution duration
   - `status` - RUNNING, SUCCESS, FAILED
   - `error_message` - Error message if failed
   - `parameters_json` - JSON representation of input parameters
   - `result_count` - Number of rows returned
   - `triggered_by` - Who/what triggered execution

### Management Procedures

1. **`[Data].[ctl_usp_register_procedure]`** - Register or update a procedure
2. **`[Data].[ctl_usp_register_procedure_parameter]`** - Register or update a parameter
3. **`[Data].[ctl_usp_log_procedure_execution]`** - Log procedure execution (start/finish)
4. **`[Data].[ctl_usp_get_procedure_info]`** - Get detailed procedure information
5. **`[Data].[ctl_usp_list_procedures]`** - List procedures with filtering

## Setup

### 1. Run Migration

Execute the migration script to create the tables:

```sql
-- Run in order
sql/00_migrations/060_procedure_catalog.sql
```

### 2. Deploy Management Procedures

Deploy the management procedures:

```sql
sql/10_routines/procedures/ctl_procedure_catalog_management.sql
```

### 3. Seed Existing Procedures

Populate the catalog with existing procedures:

```sql
sql/10_routines/procedures/ctl_procedure_catalog_seed.sql
```

## Usage Examples

### Registering a New Procedure

```sql
-- Register the procedure
EXEC [Data].[ctl_usp_register_procedure]
    @procedure_name = N'[Data].[etl_usp_load_stage_factory_inventory]',
    @schema_name = N'Data',
    @procedure_category = N'ETL',
    @description = N'Load factory inventory data into staging table',
    @purpose = N'Extracts factory inventory data from source and loads into staging',
    @version = N'1.0.0',
    @is_enabled = 1,
    @created_by = N'DEVELOPER';

-- Register parameters
EXEC [Data].[ctl_usp_register_procedure_parameter]
    @procedure_name = N'[Data].[etl_usp_load_stage_factory_inventory]',
    @parameter_name = N'batch_id',
    @parameter_type = N'INPUT',
    @sql_data_type = N'BIGINT',
    @is_required = 1,
    @description = N'Batch ID for this load operation',
    @ordinal_position = 1;
```

### Logging Execution

```sql
-- Start execution
DECLARE @ExecId BIGINT;
EXEC [Data].[ctl_usp_log_procedure_execution]
    @procedure_name = N'[Data].[etl_usp_run_factory_inventory_snapshot_pipeline]',
    @execution_id = @ExecId OUTPUT,
    @batch_id = 123,
    @status = N'RUNNING',
    @triggered_by = N'SCHEDULED_JOB';

-- ... execute procedure ...

-- Finish execution
EXEC [Data].[ctl_usp_log_procedure_execution]
    @procedure_name = N'[Data].[etl_usp_run_factory_inventory_snapshot_pipeline]',
    @execution_id = @ExecId,
    @status = N'SUCCESS',
    @result_count = 1500;
```

### Querying the Catalog

```sql
-- List all ETL procedures
EXEC [Data].[ctl_usp_list_procedures]
    @procedure_category = N'ETL',
    @is_enabled = 1;

-- Get detailed procedure information
EXEC [Data].[ctl_usp_get_procedure_info]
    @procedure_name = N'[Data].[etl_usp_run_factory_inventory_snapshot_pipeline]';

-- Search procedures
EXEC [Data].[ctl_usp_list_procedures]
    @search_term = N'factory_inventory';
```

## Integration with Python Code

The catalog can be queried from Python to discover available procedures and their parameters:

```python
# Example: Query procedure catalog
results = self.execute_procedure(
    '[Data].[ctl_usp_list_procedures]',
    parameters={'procedure_category': 'ETL', 'is_enabled': 1}
)

# Example: Get procedure details before execution
procedure_info = self.execute_procedure(
    '[Data].[ctl_usp_get_procedure_info]',
    parameters={'procedure_name': '[Data].[etl_usp_run_factory_inventory_snapshot_pipeline]'}
)
```

## Benefits

1. **Centralized Documentation** - All procedure metadata in one place
2. **Discovery** - Easy to find and list available procedures
3. **Parameter Documentation** - Clear documentation of parameters and their types
4. **Version Tracking** - Track procedure versions over time
5. **Enable/Disable** - Control which procedures are active
6. **Execution History** - Optional tracking of procedure executions
7. **Integration** - Links to batch runs for end-to-end tracking

## Maintenance

- Update procedure metadata when procedures change
- Increment version numbers for significant changes
- Keep parameter definitions in sync with actual procedure signatures
- Regularly review and update descriptions/purpose fields
- Archive or disable deprecated procedures rather than deleting

## Category Guidelines

- **CTL** - Control procedures (batch management, watermarks, etc.)
- **ETL** - ETL pipeline procedures (extract, load, transform)
- **OPT** - Optimization procedures
- **RPT** - Reporting procedures

Add new categories as needed, but maintain consistency across the system.
