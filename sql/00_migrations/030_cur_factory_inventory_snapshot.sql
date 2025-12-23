/*
Purpose: Create curated snapshot table for factory inventory used by optimization logic.
Grain: One row per (snapshot_date, factory_id, product_id) combination.
Assumptions: T-SQL on SQL Server; `cur` schema already exists (see 000_init_schemas.sql); requires permissions to create tables and indexes.
Usage: This table stores trusted point-in-time snapshots of factory inventory levels, typically refreshed weekly from staging data. The snapshot_date represents the as-of date for the inventory levels. Used by downstream optimization processes that require consistent, validated inventory data.
How to run: Execute in SSMS or via sqlcmd against the target database; script is idempotent.
*/

-- Create cur.FactoryInventorySnapshot if missing
IF NOT EXISTS (
    SELECT 1
    FROM sys.tables t
    JOIN sys.schemas s ON t.schema_id = s.schema_id
    WHERE s.name = N'cur' AND t.name = N'FactoryInventorySnapshot'
)
BEGIN
    CREATE TABLE cur.FactoryInventorySnapshot (
        snapshot_date DATE NOT NULL,
        factory_id INT NOT NULL,
        product_id INT NOT NULL,
        on_hand_qty DECIMAL(18, 3) NOT NULL,
        batch_id BIGINT NOT NULL,
        created_at DATETIME2 NOT NULL CONSTRAINT DF_FactoryInventorySnapshot_created_at DEFAULT SYSUTCDATETIME(),
        CONSTRAINT PK_FactoryInventorySnapshot PRIMARY KEY (snapshot_date, factory_id, product_id)
    );
END;
GO

-- Index to support queries for latest snapshot by date
IF NOT EXISTS (
    SELECT 1
    FROM sys.indexes i
    JOIN sys.tables t ON i.object_id = t.object_id
    JOIN sys.schemas s ON t.schema_id = s.schema_id
    WHERE s.name = N'cur' AND t.name = N'FactoryInventorySnapshot' AND i.name = N'IX_FactoryInventorySnapshot_SnapshotDate'
)
BEGIN
    CREATE NONCLUSTERED INDEX IX_FactoryInventorySnapshot_SnapshotDate
        ON cur.FactoryInventorySnapshot (snapshot_date DESC);
END;
GO

