/*
Purpose: Create procedure catalog tables for storing and managing stored procedure metadata, parameters, and execution history.
Assumptions: T-SQL on SQL Server; [Data] schema already exists; requires permissions to create tables and indexes.
Usage: This catalog enables tracking of all stored procedures in the system, their parameters, documentation, and execution history. Supports procedure discovery, versioning, and operational monitoring.
How to run: Execute in SSMS or via sqlcmd against the target database; script is idempotent.
*/

-- Create [Data].[ctl_ProcedureCatalog] if missing
IF OBJECT_ID(N'[Data].[ctl_ProcedureCatalog]', 'U') IS NULL
BEGIN
    CREATE TABLE [Data].[ctl_ProcedureCatalog] (
        procedure_name NVARCHAR(200) NOT NULL CONSTRAINT PK_ProcedureCatalog PRIMARY KEY,
        schema_name NVARCHAR(128) NOT NULL, -- e.g., 'Data'
        procedure_category NVARCHAR(50) NOT NULL, -- e.g., 'ETL', 'CTL', 'DQ', 'OPT'
        description NVARCHAR(1000) NULL,
        purpose NVARCHAR(MAX) NULL, -- Detailed purpose/usage documentation
        is_enabled BIT NOT NULL CONSTRAINT DF_ProcedureCatalog_is_enabled DEFAULT 1,
        version NVARCHAR(20) NULL, -- e.g., '1.0.0'
        created_at DATETIME2 NOT NULL CONSTRAINT DF_ProcedureCatalog_created_at DEFAULT SYSUTCDATETIME(),
        updated_at DATETIME2 NOT NULL CONSTRAINT DF_ProcedureCatalog_updated_at DEFAULT SYSUTCDATETIME(),
        created_by NVARCHAR(100) NULL,
        notes NVARCHAR(MAX) NULL -- Additional notes, dependencies, etc.
    );
END;
GO

-- Create [Data].[ctl_ProcedureParameter] if missing
IF OBJECT_ID(N'[Data].[ctl_ProcedureParameter]', 'U') IS NULL
BEGIN
    CREATE TABLE [Data].[ctl_ProcedureParameter] (
        parameter_id BIGINT IDENTITY(1,1) NOT NULL CONSTRAINT PK_ProcedureParameter PRIMARY KEY,
        procedure_name NVARCHAR(200) NOT NULL,
        parameter_name NVARCHAR(128) NOT NULL, -- e.g., 'snapshot_date', '@snapshot_date' (stored without @)
        parameter_type NVARCHAR(50) NOT NULL, -- 'INPUT', 'OUTPUT', 'INPUT_OUTPUT'
        sql_data_type NVARCHAR(128) NULL, -- e.g., 'DATE', 'NVARCHAR(100)', 'BIGINT'
        is_required BIT NOT NULL CONSTRAINT DF_ProcedureParameter_is_required DEFAULT 1,
        default_value NVARCHAR(500) NULL, -- Default value if any
        description NVARCHAR(1000) NULL,
        ordinal_position INT NOT NULL, -- Order of parameter in procedure signature
        created_at DATETIME2 NOT NULL CONSTRAINT DF_ProcedureParameter_created_at DEFAULT SYSUTCDATETIME()
    );
END;
GO

-- Create [Data].[ctl_ProcedureExecution] if missing (optional: for execution history tracking)
IF OBJECT_ID(N'[Data].[ctl_ProcedureExecution]', 'U') IS NULL
BEGIN
    CREATE TABLE [Data].[ctl_ProcedureExecution] (
        execution_id BIGINT IDENTITY(1,1) NOT NULL CONSTRAINT PK_ProcedureExecution PRIMARY KEY,
        procedure_name NVARCHAR(200) NOT NULL,
        batch_id BIGINT NULL, -- Link to [Data].[ctl_BatchRun] if executed as part of a batch
        started_at DATETIME2 NOT NULL CONSTRAINT DF_ProcedureExecution_started_at DEFAULT SYSUTCDATETIME(),
        finished_at DATETIME2 NULL,
        duration_ms INT NULL, -- Duration in milliseconds
        status NVARCHAR(20) NOT NULL CONSTRAINT DF_ProcedureExecution_status DEFAULT N'RUNNING', -- RUNNING/SUCCESS/FAILED
        error_message NVARCHAR(4000) NULL,
        parameters_json NVARCHAR(MAX) NULL, -- JSON representation of input parameters
        result_count INT NULL, -- Number of rows returned (if applicable)
        triggered_by NVARCHAR(100) NULL, -- e.g., 'SCHEDULED_JOB', 'MANUAL', 'API'
        created_at DATETIME2 NOT NULL CONSTRAINT DF_ProcedureExecution_created_at DEFAULT SYSUTCDATETIME()
    );
END;
GO

-- Index on procedure_category for [Data].[ctl_ProcedureCatalog]
IF NOT EXISTS (
    SELECT 1
    FROM sys.indexes i
    WHERE i.object_id = OBJECT_ID(N'[Data].[ctl_ProcedureCatalog]', 'U')
      AND i.name = N'IX_ProcedureCatalog_Category'
)
BEGIN
    CREATE NONCLUSTERED INDEX IX_ProcedureCatalog_Category
        ON [Data].[ctl_ProcedureCatalog] (procedure_category, is_enabled);
END;
GO

-- Index on procedure_name for [Data].[ctl_ProcedureParameter]
IF NOT EXISTS (
    SELECT 1
    FROM sys.indexes i
    WHERE i.object_id = OBJECT_ID(N'[Data].[ctl_ProcedureParameter]', 'U')
      AND i.name = N'IX_ProcedureParameter_ProcedureName'
)
BEGIN
    CREATE NONCLUSTERED INDEX IX_ProcedureParameter_ProcedureName
        ON [Data].[ctl_ProcedureParameter] (procedure_name, ordinal_position);
END;
GO

-- Index on procedure_name for [Data].[ctl_ProcedureExecution]
IF NOT EXISTS (
    SELECT 1
    FROM sys.indexes i
    WHERE i.object_id = OBJECT_ID(N'[Data].[ctl_ProcedureExecution]', 'U')
      AND i.name = N'IX_ProcedureExecution_ProcedureName'
)
BEGIN
    CREATE NONCLUSTERED INDEX IX_ProcedureExecution_ProcedureName
        ON [Data].[ctl_ProcedureExecution] (procedure_name, started_at DESC);
END;
GO

-- Index on batch_id for [Data].[ctl_ProcedureExecution]
IF NOT EXISTS (
    SELECT 1
    FROM sys.indexes i
    WHERE i.object_id = OBJECT_ID(N'[Data].[ctl_ProcedureExecution]', 'U')
      AND i.name = N'IX_ProcedureExecution_BatchId'
)
BEGIN
    CREATE NONCLUSTERED INDEX IX_ProcedureExecution_BatchId
        ON [Data].[ctl_ProcedureExecution] (batch_id);
END;
GO

-- Index on started_at for [Data].[ctl_ProcedureExecution] (for recent executions)
IF NOT EXISTS (
    SELECT 1
    FROM sys.indexes i
    WHERE i.object_id = OBJECT_ID(N'[Data].[ctl_ProcedureExecution]', 'U')
      AND i.name = N'IX_ProcedureExecution_StartedAt'
)
BEGIN
    CREATE NONCLUSTERED INDEX IX_ProcedureExecution_StartedAt
        ON [Data].[ctl_ProcedureExecution] (started_at DESC);
END;
GO

-- Foreign key from [Data].[ctl_ProcedureParameter] to [Data].[ctl_ProcedureCatalog]
IF OBJECT_ID(N'[Data].[ctl_ProcedureCatalog]', 'U') IS NOT NULL
AND OBJECT_ID(N'[Data].[ctl_ProcedureParameter]', 'U') IS NOT NULL
AND NOT EXISTS (
    SELECT 1
    FROM sys.foreign_keys fk
    WHERE fk.parent_object_id = OBJECT_ID(N'[Data].[ctl_ProcedureParameter]', 'U')
      AND fk.name = N'FK_ProcedureParameter_ProcedureCatalog'
)
BEGIN
    BEGIN TRY
        ALTER TABLE [Data].[ctl_ProcedureParameter]
            ADD CONSTRAINT FK_ProcedureParameter_ProcedureCatalog
            FOREIGN KEY (procedure_name) REFERENCES [Data].[ctl_ProcedureCatalog] (procedure_name)
            ON DELETE CASCADE;
    END TRY
    BEGIN CATCH
        PRINT 'Warning: Could not create FK_ProcedureParameter_ProcedureCatalog constraint. Skipping.';
    END CATCH
END;
GO

-- Foreign key from [Data].[ctl_ProcedureExecution] to [Data].[ctl_ProcedureCatalog]
IF OBJECT_ID(N'[Data].[ctl_ProcedureCatalog]', 'U') IS NOT NULL
AND OBJECT_ID(N'[Data].[ctl_ProcedureExecution]', 'U') IS NOT NULL
AND NOT EXISTS (
    SELECT 1
    FROM sys.foreign_keys fk
    WHERE fk.parent_object_id = OBJECT_ID(N'[Data].[ctl_ProcedureExecution]', 'U')
      AND fk.name = N'FK_ProcedureExecution_ProcedureCatalog'
)
BEGIN
    BEGIN TRY
        ALTER TABLE [Data].[ctl_ProcedureExecution]
            ADD CONSTRAINT FK_ProcedureExecution_ProcedureCatalog
            FOREIGN KEY (procedure_name) REFERENCES [Data].[ctl_ProcedureCatalog] (procedure_name);
    END TRY
    BEGIN CATCH
        PRINT 'Warning: Could not create FK_ProcedureExecution_ProcedureCatalog constraint. Skipping.';
    END CATCH
END;
GO

-- Optional: Foreign key from [Data].[ctl_ProcedureExecution] to [Data].[ctl_BatchRun]
IF OBJECT_ID(N'[Data].[ctl_BatchRun]', 'U') IS NOT NULL
AND OBJECT_ID(N'[Data].[ctl_ProcedureExecution]', 'U') IS NOT NULL
AND NOT EXISTS (
    SELECT 1
    FROM sys.foreign_keys fk
    WHERE fk.parent_object_id = OBJECT_ID(N'[Data].[ctl_ProcedureExecution]', 'U')
      AND fk.name = N'FK_ProcedureExecution_BatchRun'
)
BEGIN
    BEGIN TRY
        ALTER TABLE [Data].[ctl_ProcedureExecution]
            ADD CONSTRAINT FK_ProcedureExecution_BatchRun
            FOREIGN KEY (batch_id) REFERENCES [Data].[ctl_BatchRun] (batch_id);
    END TRY
    BEGIN CATCH
        PRINT 'Warning: Could not create FK_ProcedureExecution_BatchRun constraint. Skipping.';
    END CATCH
END;
GO

