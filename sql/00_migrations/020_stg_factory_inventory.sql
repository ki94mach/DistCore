/*
Purpose: Create staging landing table for weekly factory inventory loads.
Assumptions: T-SQL on SQL Server; `stg` schema already exists (see 000_init_schemas.sql); requires permissions to create tables and indexes.
How to run: Execute in SSMS or via sqlcmd against the target database; script is idempotent.
*/

-- Create stg.FactoryInventory if missing
IF NOT EXISTS (
    SELECT 1
    FROM sys.tables t
    JOIN sys.schemas s ON t.schema_id = s.schema_id
    WHERE s.name = N'stg' AND t.name = N'FactoryInventory'
)
BEGIN
    CREATE TABLE stg.FactoryInventory (
        batch_id BIGINT NOT NULL,
        ingested_at DATETIME2 NOT NULL CONSTRAINT DF_FactoryInventory_ingested_at DEFAULT SYSUTCDATETIME(),
        factory_id INT NOT NULL,
        product_id INT NOT NULL,
        as_of_datetime DATETIME2 NULL,
        on_hand_qty DECIMAL(18, 3) NULL,
        source_system NVARCHAR(50) NULL CONSTRAINT DF_FactoryInventory_source_system DEFAULT N'DWOrchid',
        source_table NVARCHAR(128) NULL CONSTRAINT DF_FactoryInventory_source_table DEFAULT N'dbo.FactFactoryInventory',
        row_hash VARBINARY(32) NULL
    );
END;
GO

-- Clustered index for batch and dimensional access patterns
IF NOT EXISTS (
    SELECT 1
    FROM sys.indexes i
    JOIN sys.tables t ON i.object_id = t.object_id
    JOIN sys.schemas s ON t.schema_id = s.schema_id
    WHERE s.name = N'stg' AND t.name = N'FactoryInventory' AND i.name = N'CI_FactoryInventory_Batch_Factory_Product'
)
BEGIN
    CREATE CLUSTERED INDEX CI_FactoryInventory_Batch_Factory_Product
        ON stg.FactoryInventory (batch_id, factory_id, product_id);
END;
GO

-- Nonclustered index to support lookups by factory/product with load context
IF NOT EXISTS (
    SELECT 1
    FROM sys.indexes i
    JOIN sys.tables t ON i.object_id = t.object_id
    JOIN sys.schemas s ON t.schema_id = s.schema_id
    WHERE s.name = N'stg' AND t.name = N'FactoryInventory' AND i.name = N'IX_FactoryInventory_Factory_Product_Incl'
)
BEGIN
    CREATE NONCLUSTERED INDEX IX_FactoryInventory_Factory_Product_Incl
        ON stg.FactoryInventory (factory_id, product_id)
        INCLUDE (on_hand_qty, as_of_datetime, batch_id);
END;
GO

