/*
Purpose: Create snapshot table for factory inventory used by optimization logic.
Grain: One row per (snapshot_date, product_id) combination.
Assumptions: T-SQL on SQL Server; [Data] schema already exists; requires permissions to create tables and indexes.
Usage: This table stores point-in-time snapshots of factory inventory levels, typically refreshed
       from DWOrchid via etl_usp_build_factory_inventory_snapshot. The snapshot_date is both the
       source FKDate filter and the as-of key. Data is aggregated by product_id, summing quantities
       across all factories. Used by downstream optimization processes.
How to run: Execute in SSMS or via sqlcmd against the target database; script is idempotent.
*/

-- Create [$(prod_schema)].[snp_FactoryInventorySnapshot] if missing
IF OBJECT_ID(N'[$(prod_schema)].[snp_FactoryInventorySnapshot]', 'U') IS NULL
BEGIN
    CREATE TABLE [$(prod_schema)].[snp_FactoryInventorySnapshot] (
        snapshot_date DATE NOT NULL,
        product_id INT NOT NULL,
        on_hand_qty BIGINT NULL,
        batch_id BIGINT NOT NULL,
        created_at DATETIME2 NOT NULL CONSTRAINT DF_FactoryInventorySnapshot_created_at DEFAULT SYSUTCDATETIME(),
        CONSTRAINT PK_FactoryInventorySnapshot PRIMARY KEY (snapshot_date, product_id)
    );
END;
GO

-- Migration: Update existing table structure if it has old schema
IF EXISTS (
    SELECT 1
    FROM sys.columns c
    WHERE c.object_id = OBJECT_ID(N'[$(prod_schema)].[snp_FactoryInventorySnapshot]', 'U')
      AND c.name = N'factory_id'
)
BEGIN
    -- Drop old primary key if it exists
    IF EXISTS (
        SELECT 1
        FROM sys.key_constraints kc
        WHERE kc.parent_object_id = OBJECT_ID(N'[$(prod_schema)].[snp_FactoryInventorySnapshot]', 'U')
          AND kc.name = N'PK_FactoryInventorySnapshot'
    )
    BEGIN
        ALTER TABLE [$(prod_schema)].[snp_FactoryInventorySnapshot]
            DROP CONSTRAINT PK_FactoryInventorySnapshot;
    END;
    
    -- Drop old index if it exists
    IF EXISTS (
        SELECT 1
        FROM sys.indexes i
        WHERE i.object_id = OBJECT_ID(N'[$(prod_schema)].[snp_FactoryInventorySnapshot]', 'U')
          AND i.name = N'IX_FactoryInventorySnapshot_SnapshotDate'
    )
    BEGIN
        DROP INDEX IX_FactoryInventorySnapshot_SnapshotDate ON [$(prod_schema)].[snp_FactoryInventorySnapshot];
    END;
    
    -- Aggregate existing data by (snapshot_date, product_id) before schema change
    -- Create temporary table with aggregated data
    SELECT 
        snapshot_date,
        product_id,
        SUM(on_hand_qty) AS on_hand_qty,
        MAX(batch_id) AS batch_id,
        MIN(created_at) AS created_at
    INTO #TempAggregatedSnapshot
    FROM [$(prod_schema)].[snp_FactoryInventorySnapshot]
    GROUP BY snapshot_date, product_id;
    
    -- Clear existing table
    TRUNCATE TABLE [$(prod_schema)].[snp_FactoryInventorySnapshot];
    
    -- Drop old columns
    ALTER TABLE [$(prod_schema)].[snp_FactoryInventorySnapshot]
        DROP COLUMN factory_id;
    
    IF EXISTS (
        SELECT 1
        FROM sys.columns c
        WHERE c.object_id = OBJECT_ID(N'[$(prod_schema)].[snp_FactoryInventorySnapshot]', 'U')
          AND c.name = N'product_batch_no'
    )
    BEGIN
        ALTER TABLE [$(prod_schema)].[snp_FactoryInventorySnapshot]
            DROP COLUMN product_batch_no;
    END;
    
    -- Add new primary key
    ALTER TABLE [$(prod_schema)].[snp_FactoryInventorySnapshot]
        ADD CONSTRAINT PK_FactoryInventorySnapshot PRIMARY KEY (snapshot_date, product_id);
    
    -- Re-insert aggregated data
    INSERT INTO [$(prod_schema)].[snp_FactoryInventorySnapshot] (snapshot_date, product_id, on_hand_qty, batch_id, created_at)
    SELECT snapshot_date, product_id, on_hand_qty, batch_id, created_at
    FROM #TempAggregatedSnapshot;
    
    -- Drop temporary table
    DROP TABLE #TempAggregatedSnapshot;
END;
GO

-- Index to support queries for latest snapshot by date
IF NOT EXISTS (
    SELECT 1
    FROM sys.indexes i
    WHERE i.object_id = OBJECT_ID(N'[$(prod_schema)].[snp_FactoryInventorySnapshot]', 'U')
      AND i.name = N'IX_FactoryInventorySnapshot_SnapshotDate'
)
BEGIN
    CREATE NONCLUSTERED INDEX IX_FactoryInventorySnapshot_SnapshotDate
        ON [$(prod_schema)].[snp_FactoryInventorySnapshot] (snapshot_date DESC);
END;
GO
