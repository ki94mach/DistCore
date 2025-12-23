/*
Purpose: Create data quality tables for rule cataloging, validation result tracking, and record quarantine.
Assumptions: T-SQL on SQL Server; `dq` schema already exists (see 000_init_schemas.sql); requires permissions to create tables and indexes.
How to run: Execute in SSMS or via sqlcmd against the target database; script is idempotent.
*/

-- Create dq.RuleCatalog if missing
IF NOT EXISTS (
    SELECT 1
    FROM sys.tables t
    JOIN sys.schemas s ON t.schema_id = s.schema_id
    WHERE s.name = N'dq' AND t.name = N'RuleCatalog'
)
BEGIN
    CREATE TABLE dq.RuleCatalog (
        rule_name NVARCHAR(200) NOT NULL CONSTRAINT PK_RuleCatalog PRIMARY KEY,
        target_object NVARCHAR(200) NOT NULL,
        severity NVARCHAR(10) NOT NULL, -- HARD/SOFT
        description NVARCHAR(1000) NULL,
        is_enabled BIT NOT NULL CONSTRAINT DF_RuleCatalog_is_enabled DEFAULT 1,
        created_at DATETIME2 NOT NULL CONSTRAINT DF_RuleCatalog_created_at DEFAULT SYSUTCDATETIME()
    );
END;
GO

-- Create dq.ValidationResult if missing
IF NOT EXISTS (
    SELECT 1
    FROM sys.tables t
    JOIN sys.schemas s ON t.schema_id = s.schema_id
    WHERE s.name = N'dq' AND t.name = N'ValidationResult'
)
BEGIN
    CREATE TABLE dq.ValidationResult (
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

-- Index on batch_id for dq.ValidationResult
IF NOT EXISTS (
    SELECT 1
    FROM sys.indexes i
    JOIN sys.tables t ON i.object_id = t.object_id
    JOIN sys.schemas s ON t.schema_id = s.schema_id
    WHERE s.name = N'dq' AND t.name = N'ValidationResult' AND i.name = N'IX_ValidationResult_BatchId'
)
BEGIN
    CREATE NONCLUSTERED INDEX IX_ValidationResult_BatchId
        ON dq.ValidationResult (batch_id);
END;
GO

-- Index on rule_name for dq.ValidationResult
IF NOT EXISTS (
    SELECT 1
    FROM sys.indexes i
    JOIN sys.tables t ON i.object_id = t.object_id
    JOIN sys.schemas s ON t.schema_id = s.schema_id
    WHERE s.name = N'dq' AND t.name = N'ValidationResult' AND i.name = N'IX_ValidationResult_RuleName'
)
BEGIN
    CREATE NONCLUSTERED INDEX IX_ValidationResult_RuleName
        ON dq.ValidationResult (rule_name);
END;
GO

-- Index on severity for dq.ValidationResult
IF NOT EXISTS (
    SELECT 1
    FROM sys.indexes i
    JOIN sys.tables t ON i.object_id = t.object_id
    JOIN sys.schemas s ON t.schema_id = s.schema_id
    WHERE s.name = N'dq' AND t.name = N'ValidationResult' AND i.name = N'IX_ValidationResult_Severity'
)
BEGIN
    CREATE NONCLUSTERED INDEX IX_ValidationResult_Severity
        ON dq.ValidationResult (severity);
END;
GO

-- Optional FK from dq.ValidationResult.rule_name to dq.RuleCatalog.rule_name
IF EXISTS (
    SELECT 1
    FROM sys.tables t
    JOIN sys.schemas s ON t.schema_id = s.schema_id
    WHERE s.name = N'dq' AND t.name = N'RuleCatalog'
)
AND EXISTS (
    SELECT 1
    FROM sys.tables t
    JOIN sys.schemas s ON t.schema_id = s.schema_id
    WHERE s.name = N'dq' AND t.name = N'ValidationResult'
)
AND NOT EXISTS (
    SELECT 1
    FROM sys.foreign_keys fk
    JOIN sys.tables t ON fk.parent_object_id = t.object_id
    JOIN sys.schemas s ON t.schema_id = s.schema_id
    WHERE s.name = N'dq' AND t.name = N'ValidationResult' AND fk.name = N'FK_ValidationResult_RuleCatalog'
)
BEGIN
    ALTER TABLE dq.ValidationResult
        ADD CONSTRAINT FK_ValidationResult_RuleCatalog
        FOREIGN KEY (rule_name) REFERENCES dq.RuleCatalog (rule_name);
END;
GO

-- Create dq.Quarantine_FactoryInventory if missing
IF NOT EXISTS (
    SELECT 1
    FROM sys.tables t
    JOIN sys.schemas s ON t.schema_id = s.schema_id
    WHERE s.name = N'dq' AND t.name = N'Quarantine_FactoryInventory'
)
BEGIN
    CREATE TABLE dq.Quarantine_FactoryInventory (
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

-- Index on batch_id for dq.Quarantine_FactoryInventory
IF NOT EXISTS (
    SELECT 1
    FROM sys.indexes i
    JOIN sys.tables t ON i.object_id = t.object_id
    JOIN sys.schemas s ON t.schema_id = s.schema_id
    WHERE s.name = N'dq' AND t.name = N'Quarantine_FactoryInventory' AND i.name = N'IX_Quarantine_FactoryInventory_BatchId'
)
BEGIN
    CREATE NONCLUSTERED INDEX IX_Quarantine_FactoryInventory_BatchId
        ON dq.Quarantine_FactoryInventory (batch_id);
END;
GO

