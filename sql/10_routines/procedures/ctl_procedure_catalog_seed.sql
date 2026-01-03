/*
Purpose: Seed [Data].[ctl_ProcedureCatalog] and [Data].[ctl_ProcedureParameter] with existing stored procedures.
Assumptions: T-SQL on SQL Server; [Data] schema and procedure catalog tables exist (see 060_procedure_catalog.sql); procedures must exist in the database; requires permissions to INSERT/UPDATE into catalog tables.
Usage: This script is idempotent: re-running will update existing procedure metadata if changed, or leave them unchanged if identical. Safe to execute multiple times.
How to run: Execute in SSMS or via sqlcmd against the target database. Should be run after 060_procedure_catalog.sql migration.
*/

-- Seed procedure catalog with existing procedures using MERGE for idempotent upsert
MERGE [Data].[ctl_ProcedureCatalog] AS target
USING (
    -- Control procedures
    SELECT N'[Data].[ctl_usp_start_batch]' AS procedure_name, N'Data' AS schema_name, N'CTL' AS procedure_category,
           N'Insert a new batch run record and return the generated batch_id' AS description,
           N'Provides a standardized way to track batch execution lifecycle. Use at the beginning of a batch process.' AS purpose,
           1 AS is_enabled, N'1.0.0' AS version, N'SYSTEM' AS created_by,
           N'Requires [Data].[ctl_BatchRun] table. Returns batch_id via OUTPUT parameter.' AS notes
    UNION ALL
    SELECT N'[Data].[ctl_usp_finish_batch]', N'Data', N'CTL',
           N'Update a batch run record with completion status and message',
           N'Provides a standardized way to finalize batch execution. Use at the end of a batch process (success or failure).',
           1, N'1.0.0', N'SYSTEM',
           N'Requires [Data].[ctl_BatchRun] table. Updates existing batch record with status and completion time.'
    UNION ALL
    -- ETL procedures
    SELECT N'[Data].[etl_usp_run_factory_inventory_snapshot_pipeline]', N'Data', N'ETL',
           N'Orchestrate the complete factory inventory ETL pipeline from staging load through snapshot publication',
           N'Main entry point for running the factory inventory ETL pipeline. Coordinates all steps: batch tracking, staging load, and snapshot publication. Errors bubble up via THROW for Python callers to handle.',
           1, N'1.0.0', N'SYSTEM',
           N'Depends on: ctl_usp_start_batch, ctl_usp_finish_batch, etl_usp_load_stage_factory_inventory, etl_usp_build_factory_inventory_snapshot'
) AS source
ON target.procedure_name = source.procedure_name
WHEN MATCHED THEN
    UPDATE SET
        schema_name = source.schema_name,
        procedure_category = source.procedure_category,
        description = source.description,
        purpose = source.purpose,
        is_enabled = source.is_enabled,
        version = source.version,
        updated_at = SYSUTCDATETIME(),
        notes = source.notes
        -- Note: created_at and created_by are preserved to maintain original creation metadata
WHEN NOT MATCHED BY TARGET THEN
    INSERT (procedure_name, schema_name, procedure_category, description, purpose, is_enabled, version, created_by, notes)
    VALUES (source.procedure_name, source.schema_name, source.procedure_category, source.description, source.purpose, source.is_enabled, source.version, source.created_by, source.notes);
GO

-- Seed procedure parameters for ctl_usp_start_batch
MERGE [Data].[ctl_ProcedureParameter] AS target
USING (
    SELECT N'[Data].[ctl_usp_start_batch]' AS procedure_name, N'batch_type' AS parameter_name, N'INPUT' AS parameter_type,
           N'NVARCHAR(50)' AS sql_data_type, 1 AS is_required, NULL AS default_value,
           N'Type of batch being executed (e.g., FACTORY_INVENTORY)' AS description, 1 AS ordinal_position
    UNION ALL
    SELECT N'[Data].[ctl_usp_start_batch]', N'triggered_by', N'INPUT', N'NVARCHAR(100)', 0, NULL,
           N'Optional identifier for who/what triggered this batch (e.g., SCHEDULED_JOB, MANUAL, API)', 2
    UNION ALL
    SELECT N'[Data].[ctl_usp_start_batch]', N'batch_id', N'OUTPUT', N'BIGINT', 1, NULL,
           N'Generated batch_id returned to caller', 3
) AS source
ON target.procedure_name = source.procedure_name AND target.parameter_name = source.parameter_name
WHEN MATCHED THEN
    UPDATE SET
        parameter_type = source.parameter_type,
        sql_data_type = source.sql_data_type,
        is_required = source.is_required,
        default_value = source.default_value,
        description = source.description,
        ordinal_position = source.ordinal_position
WHEN NOT MATCHED BY TARGET THEN
    INSERT (procedure_name, parameter_name, parameter_type, sql_data_type, is_required, default_value, description, ordinal_position)
    VALUES (source.procedure_name, source.parameter_name, source.parameter_type, source.sql_data_type, source.is_required, source.default_value, source.description, source.ordinal_position);
GO

-- Seed procedure parameters for ctl_usp_finish_batch
MERGE [Data].[ctl_ProcedureParameter] AS target
USING (
    SELECT N'[Data].[ctl_usp_finish_batch]' AS procedure_name, N'batch_id' AS parameter_name, N'INPUT' AS parameter_type,
           N'BIGINT' AS sql_data_type, 1 AS is_required, NULL AS default_value,
           N'Batch ID to update' AS description, 1 AS ordinal_position
    UNION ALL
    SELECT N'[Data].[ctl_usp_finish_batch]', N'status', N'INPUT', N'NVARCHAR(20)', 1, NULL,
           N'Completion status (SUCCESS, FAILED, PARTIAL)' AS description, 2
    UNION ALL
    SELECT N'[Data].[ctl_usp_finish_batch]', N'message', N'INPUT', N'NVARCHAR(4000)', 0, NULL,
           N'Optional message describing the batch completion' AS description, 3
) AS source
ON target.procedure_name = source.procedure_name AND target.parameter_name = source.parameter_name
WHEN MATCHED THEN
    UPDATE SET
        parameter_type = source.parameter_type,
        sql_data_type = source.sql_data_type,
        is_required = source.is_required,
        default_value = source.default_value,
        description = source.description,
        ordinal_position = source.ordinal_position
WHEN NOT MATCHED BY TARGET THEN
    INSERT (procedure_name, parameter_name, parameter_type, sql_data_type, is_required, default_value, description, ordinal_position)
    VALUES (source.procedure_name, source.parameter_name, source.parameter_type, source.sql_data_type, source.is_required, source.default_value, source.description, source.ordinal_position);
GO

-- Seed procedure parameters for etl_usp_run_factory_inventory_snapshot_pipeline
MERGE [Data].[ctl_ProcedureParameter] AS target
USING (
    SELECT N'[Data].[etl_usp_run_factory_inventory_snapshot_pipeline]' AS procedure_name, N'snapshot_date' AS parameter_name, N'INPUT' AS parameter_type,
           N'DATE' AS sql_data_type, 1 AS is_required, NULL AS default_value,
           N'The snapshot date to assign to published records in [Data].[snp_FactoryInventorySnapshot]' AS description, 1 AS ordinal_position
    UNION ALL
    SELECT N'[Data].[etl_usp_run_factory_inventory_snapshot_pipeline]', N'triggered_by', N'INPUT', N'NVARCHAR(100)', 0, NULL,
           N'Optional identifier for who/what triggered this pipeline run (e.g., SCHEDULED_JOB, MANUAL, API)', 2
) AS source
ON target.procedure_name = source.procedure_name AND target.parameter_name = source.parameter_name
WHEN MATCHED THEN
    UPDATE SET
        parameter_type = source.parameter_type,
        sql_data_type = source.sql_data_type,
        is_required = source.is_required,
        default_value = source.default_value,
        description = source.description,
        ordinal_position = source.ordinal_position
WHEN NOT MATCHED BY TARGET THEN
    INSERT (procedure_name, parameter_name, parameter_type, sql_data_type, is_required, default_value, description, ordinal_position)
    VALUES (source.procedure_name, source.parameter_name, source.parameter_type, source.sql_data_type, source.is_required, source.default_value, source.description, source.ordinal_position);
GO

-- Return summary of seeded procedures
SELECT 
    pc.procedure_name,
    pc.procedure_category,
    pc.description,
    pc.is_enabled,
    pc.version,
    COUNT(pp.parameter_id) AS parameter_count,
    pc.created_at
FROM [Data].[ctl_ProcedureCatalog] pc
LEFT JOIN [Data].[ctl_ProcedureParameter] pp ON pc.procedure_name = pp.procedure_name
GROUP BY pc.procedure_name, pc.procedure_category, pc.description, pc.is_enabled, pc.version, pc.created_at
ORDER BY pc.procedure_category, pc.procedure_name;
GO

/*
Example Usage:

-- Example 1: List all procedures by category
SELECT 
    procedure_name,
    procedure_category,
    description,
    is_enabled,
    version
FROM [Data].[ctl_ProcedureCatalog]
ORDER BY procedure_category, procedure_name;

-- Example 2: Get procedure details with parameters
SELECT 
    pc.procedure_name,
    pc.description,
    pc.purpose,
    pp.parameter_name,
    pp.parameter_type,
    pp.sql_data_type,
    pp.is_required,
    pp.default_value,
    pp.description AS parameter_description,
    pp.ordinal_position
FROM [Data].[ctl_ProcedureCatalog] pc
LEFT JOIN [Data].[ctl_ProcedureParameter] pp ON pc.procedure_name = pp.procedure_name
WHERE pc.procedure_name = N'[Data].[etl_usp_run_factory_inventory_snapshot_pipeline]'
ORDER BY pp.ordinal_position;

-- Example 3: Find procedures by category
SELECT 
    procedure_name,
    description,
    is_enabled
FROM [Data].[ctl_ProcedureCatalog]
WHERE procedure_category = N'ETL'
  AND is_enabled = 1
ORDER BY procedure_name;

-- Example 4: Check procedure execution history
SELECT 
    pe.procedure_name,
    pe.started_at,
    pe.finished_at,
    pe.duration_ms,
    pe.status,
    pe.triggered_by
FROM [Data].[ctl_ProcedureExecution] pe
WHERE pe.procedure_name = N'[Data].[etl_usp_run_factory_inventory_snapshot_pipeline]'
ORDER BY pe.started_at DESC;
*/
