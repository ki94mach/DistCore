/*
Purpose: Create snapshot table for distributor inventory used by optimization logic.
Grain: One row per (snapshot_date, distributor_id, product_id) combination.
Assumptions: T-SQL on SQL Server; [Data] schema already exists; requires permissions to create tables and indexes.
Usage: This table stores point-in-time snapshots of distributor inventory levels, typically refreshed weekly from staging data. The snapshot_date represents the as-of date for the inventory levels. Data is aggregated by product_id and distributor_id and snapshot_date, summing quantities across all centers. Used by downstream optimization processes that require consistent snapshot inputs.
How to run: Execute in SSMS or via sqlcmd against the target database; script is idempotent.
*/

-- Create [Data].[snp_DistributorInventorySnapshot] if missing
IF OBJECT_ID(N'[Data].[snp_DistributorInventorySnapshot]', 'U') IS NULL
BEGIN
    CREATE TABLE [Data].[snp_DistributorInventorySnapshot] (
        snapshot_date DATE NOT NULL,
        product_id INT NOT NULL,
        distributor_id INT NOT NULL,
        on_hand_qty BIGINT NULL,
        batch_id BIGINT NOT NULL,
        created_at DATETIME2 NOT NULL CONSTRAINT DF_DistributorInventorySnapshot_created_at DEFAULT SYSUTCDATETIME(),
        CONSTRAINT PK_DistributorInventorySnapshot PRIMARY KEY (snapshot_date, product_id, distributor_id)
    );
END;
GO

-- Migration: Update existing table structure if it has old schema
IF EXISTS (
    SELECT 1
    FROM sys.columns c
    WHERE c.object_id = OBJECT_ID(N'[Data].[snp_DistributorInventorySnapshot]', 'U')
      AND c.name = N'distributor_id'
)
BEGIN
    -- Drop old primary key if it exists
    IF EXISTS (
        SELECT 1
        FROM sys.key_constraints kc
        WHERE kc.parent_object_id = OBJECT_ID(N'[Data].[snp_DistributorInventorySnapshot]', 'U')
          AND kc.name = N'PK_DistributorInventorySnapshot'
    )
    BEGIN
        ALTER TABLE [Data].[snp_DistributorInventorySnapshot]
            DROP CONSTRAINT PK_DistributorInventorySnapshot;
    END;
    
    -- Drop old index if it exists
    IF EXISTS (
        SELECT 1
        FROM sys.indexes i
        WHERE i.object_id = OBJECT_ID(N'[Data].[snp_DistributorInventorySnapshot]', 'U')
          AND i.name = N'IX_DistributorInventorySnapshot_SnapshotDate'
    )
    BEGIN
        DROP INDEX IX_DistributorInventorySnapshot_SnapshotDate ON [Data].[snp_DistributorInventorySnapshot];
    END;
    
    -- Aggregate existing data by (snapshot_date, product_id) before schema change
    -- Create temporary table with aggregated data
    SELECT 
        snapshot_date,
        product_id,
        distributor_id,
        SUM(on_hand_qty) AS on_hand_qty,
        MAX(batch_id) AS batch_id,
        MIN(created_at) AS created_at
    INTO #TempAggregatedSnapshot
    FROM [Data].[snp_DistributorInventorySnapshot]
    GROUP BY snapshot_date, product_id, distributor_id;
    
    -- Clear existing table
    TRUNCATE TABLE [Data].[snp_DistributorInventorySnapshot];
    
    -- Drop old columns
    ALTER TABLE [Data].[snp_DistributorInventorySnapshot]
        DROP COLUMN distributor_id;
    
    IF EXISTS (
        SELECT 1
        FROM sys.columns c
        WHERE c.object_id = OBJECT_ID(N'[Data].[snp_DistributorInventorySnapshot]', 'U')
          AND c.name = N'product_batch_no'
    )
    BEGIN
        ALTER TABLE [Data].[snp_DistributorInventorySnapshot]
            DROP COLUMN product_batch_no;
    END;
    
    -- Add new primary key
    ALTER TABLE [Data].[snp_DistributorInventorySnapshot]
        ADD CONSTRAINT PK_DistributorInventorySnapshot PRIMARY KEY (snapshot_date, product_id, distributor_id);
    
    -- Re-insert aggregated data
    INSERT INTO [Data].[snp_DistributorInventorySnapshot] (snapshot_date, product_id, distributor_id, on_hand_qty, batch_id, created_at)
    SELECT snapshot_date, product_id, distributor_id, on_hand_qty, batch_id, created_at
    FROM #TempAggregatedSnapshot;
    
    -- Drop temporary table
    DROP TABLE #TempAggregatedSnapshot;
END;
GO

-- Index to support queries for latest snapshot by date
IF NOT EXISTS (
    SELECT 1
    FROM sys.indexes i
    WHERE i.object_id = OBJECT_ID(N'[Data].[snp_DistributorInventorySnapshot]', 'U')
      AND i.name = N'IX_DistributorInventorySnapshot_SnapshotDate'
)
BEGIN
    CREATE NONCLUSTERED INDEX IX_DistributorInventorySnapshot_SnapshotDate
        ON [Data].[snp_DistributorInventorySnapshot] (snapshot_date DESC);
END;
GO
