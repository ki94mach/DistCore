/*
Purpose: Create staging landing table for weekly factory inventory loads.
Assumptions: T-SQL on SQL Server; [Data] schema already exists; requires permissions to create tables and indexes.
How to run: Execute in SSMS or via sqlcmd against the target database; script is idempotent.
Note: Staging accepts imperfect rows (nullable keys) to enable snapshot transformation before the snapshot layer. Snapshot tables enforce constraints.
*/

-- Create [Data].[stg_FactoryInventory] if missing
IF OBJECT_ID(N'[Data].[stg_FactoryInventory]', 'U') IS NULL
BEGIN
    CREATE TABLE [Data].[stg_FactoryInventory] (
        batch_id BIGINT NOT NULL,
        ingested_at DATETIME2 NOT NULL CONSTRAINT DF_FactoryInventory_ingested_at DEFAULT SYSUTCDATETIME(),
        factory_id INT NULL,
        product_id INT NULL,
        product_batch_no NVARCHAR(200) NULL,
        as_of_datetime DATE NULL,
        on_hand_qty BIGINT NULL,
        source_system NVARCHAR(50) NULL CONSTRAINT DF_FactoryInventory_source_system DEFAULT N'DWOrchid',
        source_table NVARCHAR(128) NULL CONSTRAINT DF_FactoryInventory_source_table DEFAULT N'dbo.FactInventory',
        row_hash VARBINARY(32) NULL
    );
END;
GO

-- Alter existing table to make factory_id and product_id nullable (idempotent)
-- Staging accepts imperfect rows; snapshot layer enforces constraints
IF EXISTS (
    SELECT 1
    FROM sys.columns c
    WHERE c.object_id = OBJECT_ID(N'[Data].[stg_FactoryInventory]', 'U')
      AND c.name = N'factory_id' AND c.is_nullable = 0
)
BEGIN
    ALTER TABLE [Data].[stg_FactoryInventory]
        ALTER COLUMN factory_id INT NULL;
END;
GO

IF EXISTS (
    SELECT 1
    FROM sys.columns c
    WHERE c.object_id = OBJECT_ID(N'[Data].[stg_FactoryInventory]', 'U')
      AND c.name = N'product_id' AND c.is_nullable = 0
)
BEGIN
    ALTER TABLE [Data].[stg_FactoryInventory]
        ALTER COLUMN product_id INT NULL;
END;
GO

-- Clustered index for batch and dimensional access patterns
IF NOT EXISTS (
    SELECT 1
    FROM sys.indexes i
    WHERE i.object_id = OBJECT_ID(N'[Data].[stg_FactoryInventory]', 'U')
      AND i.name = N'CI_FactoryInventory_Batch_Factory_Product'
)
BEGIN
    CREATE CLUSTERED INDEX CI_FactoryInventory_Batch_Factory_Product
        ON [Data].[stg_FactoryInventory] (batch_id, factory_id, product_id);
END;
GO

-- Nonclustered index to support lookups by factory/product with load context
IF NOT EXISTS (
    SELECT 1
    FROM sys.indexes i
    WHERE i.object_id = OBJECT_ID(N'[Data].[stg_FactoryInventory]', 'U')
      AND i.name = N'IX_FactoryInventory_Factory_Product_Incl'
)
BEGIN
    CREATE NONCLUSTERED INDEX IX_FactoryInventory_Factory_Product_Incl
        ON [Data].[stg_FactoryInventory] (factory_id, product_id)
        INCLUDE (on_hand_qty, as_of_datetime, batch_id);
END;
GO
