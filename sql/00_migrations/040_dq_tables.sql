/*
Purpose: Create data quality tables for rule cataloging, validation result tracking, and record quarantine.
Assumptions: T-SQL on SQL Server; [Data] schema already exists; requires permissions to create tables and indexes.
How to run: Execute in SSMS or via sqlcmd against the target database; script is idempotent.
*/

-- Create [Data].[dq_RuleCatalog] if missing
IF OBJECT_ID(N'[Data].[dq_RuleCatalog]', 'U') IS NULL
BEGIN
    CREATE TABLE [Data].[dq_RuleCatalog] (
        rule_name NVARCHAR(200) NOT NULL CONSTRAINT PK_RuleCatalog PRIMARY KEY,
        target_object NVARCHAR(200) NOT NULL,
        severity NVARCHAR(10) NOT NULL, -- HARD/SOFT
        description NVARCHAR(1000) NULL,
        is_enabled BIT NOT NULL CONSTRAINT DF_RuleCatalog_is_enabled DEFAULT 1,
        created_at DATETIME2 NOT NULL CONSTRAINT DF_RuleCatalog_created_at DEFAULT SYSUTCDATETIME()
    );
END;
GO

-- Create [Data].[dq_ValidationResult] if missing
IF OBJECT_ID(N'[Data].[dq_ValidationResult]', 'U') IS NULL
BEGIN
    CREATE TABLE [Data].[dq_ValidationResult] (
        validation_id BIGINT IDENTITY(1,1) NOT NULL CONSTRAINT PK_ValidationResult PRIMARY KEY,
        batch_id BIGINT NOT NULL,
        rule_name NVARCHAR(200) NOT NULL,
        severity NVARCHAR(10) NOT NULL,
        failed_count BIGINT NOT NULL,
        sample_query NVARCHAR(MAX) NULL,
        created_at DATETIME2 NOT NULL CONSTRAINT DF_ValidationResult_created_at DEFAULT SYSUTCDATETIME()
    );
END;
GO

-- Index on batch_id for [Data].[dq_ValidationResult]
IF NOT EXISTS (
    SELECT 1
    FROM sys.indexes i
    WHERE i.object_id = OBJECT_ID(N'[Data].[dq_ValidationResult]', 'U')
      AND i.name = N'IX_ValidationResult_BatchId'
)
BEGIN
    CREATE NONCLUSTERED INDEX IX_ValidationResult_BatchId
        ON [Data].[dq_ValidationResult] (batch_id);
END;
GO

-- Index on rule_name for [Data].[dq_ValidationResult]
IF NOT EXISTS (
    SELECT 1
    FROM sys.indexes i
    WHERE i.object_id = OBJECT_ID(N'[Data].[dq_ValidationResult]', 'U')
      AND i.name = N'IX_ValidationResult_RuleName'
)
BEGIN
    CREATE NONCLUSTERED INDEX IX_ValidationResult_RuleName
        ON [Data].[dq_ValidationResult] (rule_name);
END;
GO

-- Index on severity for [Data].[dq_ValidationResult]
IF NOT EXISTS (
    SELECT 1
    FROM sys.indexes i
    WHERE i.object_id = OBJECT_ID(N'[Data].[dq_ValidationResult]', 'U')
      AND i.name = N'IX_ValidationResult_Severity'
)
BEGIN
    CREATE NONCLUSTERED INDEX IX_ValidationResult_Severity
        ON [Data].[dq_ValidationResult] (severity);
END;
GO

-- Unique index on (batch_id, rule_name) for [Data].[dq_ValidationResult] to prevent duplicate rows per batch and rule
-- Idempotent: rerun safety - create only if not exists
IF NOT EXISTS (
    SELECT 1
    FROM sys.indexes i
    WHERE i.object_id = OBJECT_ID(N'[Data].[dq_ValidationResult]', 'U')
      AND i.name = N'UX_ValidationResult_BatchId_RuleName'
)
BEGIN
    CREATE UNIQUE NONCLUSTERED INDEX UX_ValidationResult_BatchId_RuleName
        ON [Data].[dq_ValidationResult] (batch_id, rule_name);
END;
GO

-- Optional FK from [Data].[dq_ValidationResult].rule_name to [Data].[dq_RuleCatalog].rule_name
IF OBJECT_ID(N'[Data].[dq_RuleCatalog]', 'U') IS NOT NULL
AND OBJECT_ID(N'[Data].[dq_ValidationResult]', 'U') IS NOT NULL
AND NOT EXISTS (
    SELECT 1
    FROM sys.foreign_keys fk
    WHERE fk.parent_object_id = OBJECT_ID(N'[Data].[dq_ValidationResult]', 'U')
      AND fk.name = N'FK_ValidationResult_RuleCatalog'
)
BEGIN
    ALTER TABLE [Data].[dq_ValidationResult]
        ADD CONSTRAINT FK_ValidationResult_RuleCatalog
        FOREIGN KEY (rule_name) REFERENCES [Data].[dq_RuleCatalog] (rule_name);
END;
GO

-- Create [Data].[dq_Quarantine_FactoryInventory] if missing
IF OBJECT_ID(N'[Data].[dq_Quarantine_FactoryInventory]', 'U') IS NULL
BEGIN
    CREATE TABLE [Data].[dq_Quarantine_FactoryInventory] (
        batch_id BIGINT NOT NULL,
        reason NVARCHAR(200) NOT NULL,
        factory_id INT NULL,
        product_id INT NULL,
        as_of_datetime DATETIME2 NULL,
        on_hand_qty DECIMAL(18, 3) NULL,
        ingested_at DATETIME2 NOT NULL,
        created_at DATETIME2 NOT NULL CONSTRAINT DF_Quarantine_FactoryInventory_created_at DEFAULT SYSUTCDATETIME()
    );
END;
GO

-- Index on batch_id for [Data].[dq_Quarantine_FactoryInventory]
IF NOT EXISTS (
    SELECT 1
    FROM sys.indexes i
    WHERE i.object_id = OBJECT_ID(N'[Data].[dq_Quarantine_FactoryInventory]', 'U')
      AND i.name = N'IX_Quarantine_FactoryInventory_BatchId'
)
BEGIN
    CREATE NONCLUSTERED INDEX IX_Quarantine_FactoryInventory_BatchId
        ON [Data].[dq_Quarantine_FactoryInventory] (batch_id);
END;
GO

