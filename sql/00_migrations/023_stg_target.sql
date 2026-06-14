/*
Purpose: Create staging landing table for target loads.
Assumptions: T-SQL on SQL Server; [Data] schema already exists; requires permissions to create tables and indexes.
How to run: Execute in SSMS or via sqlcmd against the target database; script is idempotent.
Note: Staging accepts imperfect rows (nullable keys) to enable snapshot transformation before the snapshot layer. Snapshot tables enforce constraints.
*/

-- Create [$(prod_schema)].[stg_Target] if missing
IF OBJECT_ID(N'[$(prod_schema)].[stg_Target]', 'U') IS NULL
BEGIN
    CREATE TABLE [$(prod_schema)].[stg_Target] (
        batch_id BIGINT NOT NULL,
        ingested_at DATETIME2 NOT NULL CONSTRAINT DF_Target_ingested_at DEFAULT SYSUTCDATETIME(),
        product_id INT NULL,
        year INT NULL,
        month INT NULL,
        target_quantity BIGINT NULL,
        as_of_datetime DATE NULL,
        source_system NVARCHAR(50) NULL CONSTRAINT DF_Target_source_system DEFAULT N'DWOrchid',
        source_table NVARCHAR(128) NULL CONSTRAINT DF_Target_source_table DEFAULT N'dbo.FactTarget',
        row_hash VARBINARY(32) NULL
    );
END;
GO

-- Alter existing table to make product_id nullable (idempotent)
-- Staging accepts imperfect rows; snapshot layer enforces constraints
IF EXISTS (
    SELECT 1
    FROM sys.columns c
    WHERE c.object_id = OBJECT_ID(N'[$(prod_schema)].[stg_Target]', 'U')
      AND c.name = N'product_id' AND c.is_nullable = 0
)
BEGIN
    ALTER TABLE [$(prod_schema)].[stg_Target]
        ALTER COLUMN product_id INT NULL;
END;
GO

-- Clustered index for batch and dimensional access patterns
IF NOT EXISTS (
    SELECT 1
    FROM sys.indexes i
    WHERE i.object_id = OBJECT_ID(N'[$(prod_schema)].[stg_Target]', 'U')
      AND i.name = N'CI_Target_Batch_Product_Year_Month'
)
BEGIN
    CREATE CLUSTERED INDEX CI_Target_Batch_Product_Year_Month
        ON [$(prod_schema)].[stg_Target] (batch_id, product_id, year, month);
END;
GO

-- Nonclustered index to support lookups by product/year/month with load context
IF NOT EXISTS (
    SELECT 1
    FROM sys.indexes i
    WHERE i.object_id = OBJECT_ID(N'[$(prod_schema)].[stg_Target]', 'U')
      AND i.name = N'IX_Target_Product_Year_Month_Incl'
)
BEGIN
    CREATE NONCLUSTERED INDEX IX_Target_Product_Year_Month_Incl
        ON [$(prod_schema)].[stg_Target] (product_id, year, month)
        INCLUDE (target_quantity, batch_id, as_of_datetime);
END;
GO

