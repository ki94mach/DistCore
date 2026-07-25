/*
Purpose: Create snapshot table for distributor inventory used by optimization logic.
Grain: One row per (snapshot_date, distributor_id, product_id) combination.
Assumptions: T-SQL on SQL Server; [Data] schema already exists; requires permissions to create tables and indexes.
Usage: This table stores point-in-time snapshots of distributor inventory levels, typically refreshed
       from DWOrchid via etl_usp_build_distributor_inventory_snapshot. The snapshot_date is both the
       source FKDate filter and the as-of key. Aggregated by product_id and distributor_id across centers.
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

-- Migration: Update existing table structure if it doesn't have distributor_id
IF NOT EXISTS (
    SELECT 1
    FROM sys.columns c
    WHERE c.object_id = OBJECT_ID(N'[Data].[snp_DistributorInventorySnapshot]', 'U')
      AND c.name = N'distributor_id'
)
BEGIN
    -- Table exists but doesn't have distributor_id - need to add it
    -- First, save existing data
    SELECT 
        snapshot_date,
        product_id,
        on_hand_qty,
        batch_id,
        created_at
    INTO #TempExistingSnapshot
    FROM [Data].[snp_DistributorInventorySnapshot];
    
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
    
    -- Drop old index if it exists (will recreate later)
    IF EXISTS (
        SELECT 1
        FROM sys.indexes i
        WHERE i.object_id = OBJECT_ID(N'[Data].[snp_DistributorInventorySnapshot]', 'U')
          AND i.name = N'IX_DistributorInventorySnapshot_SnapshotDate'
    )
    BEGIN
        DROP INDEX IX_DistributorInventorySnapshot_SnapshotDate ON [Data].[snp_DistributorInventorySnapshot];
    END;
    
    -- Drop product_batch_no if it exists (old schema)
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
    
    -- Clear existing table
    TRUNCATE TABLE [Data].[snp_DistributorInventorySnapshot];
    
    -- Add distributor_id column (default to 0 for existing rows, but we'll handle this differently)
    -- Since we can't add NOT NULL column to existing table with data, we'll add it as nullable first
    -- then update and make it NOT NULL
    ALTER TABLE [Data].[snp_DistributorInventorySnapshot]
        ADD distributor_id INT NULL;
    
    -- Re-insert existing data with a default distributor_id (0 or NULL)
    -- Note: This assumes existing data should be aggregated by product_id only
    -- If you have specific distributor_id values, you'll need to update this logic
    INSERT INTO [Data].[snp_DistributorInventorySnapshot] (snapshot_date, product_id, distributor_id, on_hand_qty, batch_id, created_at)
    SELECT 
        snapshot_date,
        product_id,
        0 AS distributor_id,  -- Default to 0 for existing rows without distributor context
        on_hand_qty,
        batch_id,
        created_at
    FROM #TempExistingSnapshot;
    
    -- Now make distributor_id NOT NULL
    ALTER TABLE [Data].[snp_DistributorInventorySnapshot]
        ALTER COLUMN distributor_id INT NOT NULL;
    
    -- Add new primary key with distributor_id
    ALTER TABLE [Data].[snp_DistributorInventorySnapshot]
        ADD CONSTRAINT PK_DistributorInventorySnapshot PRIMARY KEY (snapshot_date, product_id, distributor_id);
    
    -- Drop temporary table
    DROP TABLE #TempExistingSnapshot;
END
ELSE
BEGIN
    -- Table exists and has distributor_id - ensure primary key includes it
    -- Check if primary key exists and includes distributor_id
    IF NOT EXISTS (
        SELECT 1
        FROM sys.key_constraints kc
        INNER JOIN sys.index_columns ic ON ic.object_id = kc.parent_object_id AND ic.index_id = kc.unique_index_id
        INNER JOIN sys.columns c ON c.object_id = ic.object_id AND c.column_id = ic.column_id
        WHERE kc.parent_object_id = OBJECT_ID(N'[Data].[snp_DistributorInventorySnapshot]', 'U')
          AND kc.name = N'PK_DistributorInventorySnapshot'
          AND c.name = N'distributor_id'
    )
    BEGIN
        -- Primary key exists but doesn't include distributor_id - need to update it
        -- Drop old primary key
        ALTER TABLE [Data].[snp_DistributorInventorySnapshot]
            DROP CONSTRAINT PK_DistributorInventorySnapshot;
        
        -- Add new primary key with distributor_id
        ALTER TABLE [Data].[snp_DistributorInventorySnapshot]
            ADD CONSTRAINT PK_DistributorInventorySnapshot PRIMARY KEY (snapshot_date, product_id, distributor_id);
    END;
    
    -- Drop product_batch_no if it exists (old schema)
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
