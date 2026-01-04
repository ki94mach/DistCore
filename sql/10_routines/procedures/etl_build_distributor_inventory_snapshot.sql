/*
Purpose: Build distributor inventory snapshots from staging ([Data].[stg_DistributorInventory]) into the snapshot table ([Data].[snp_DistributorInventorySnapshot]) for a given snapshot date.
Aggregation Logic: 
    - Aggregates by (product_id, distributor_id) combination (one row per (product_id, distributor_id) combination in snapshot)
    - Sums on_hand_qty across ALL distributors for each product
    - Filters to only today's date (as_of_datetime = CAST(GETDATE() AS DATE))
    - Result: Total inventory quantity per (product_id, distributor_id) combination for today's date
Grain: One row per (snapshot_date, distributor_id, product_id) in the snapshot table. Quantities are summed across all centers.
Assumptions: T-SQL on SQL Server; staging table [Data].[stg_DistributorInventory] exists (see 020_stg_distributor_inventory.sql); snapshot table [Data].[snp_DistributorInventorySnapshot] exists (see 030_snap_distributor_inventory_snapshot.sql).
Usage: This stored procedure is typically called as part of an ETL pipeline after staging load. It aggregates staging data by product_id for today's date only, summing on_hand_qty across all distributors, and merges into the snapshot table. The procedure is idempotent: re-running with the same @batch_id and @snapshot_date will update existing records if staging data has changed, or leave them unchanged if data is identical. This allows safe reruns of the ETL pipeline without creating duplicate snapshots.
Parameters:
    @batch_id BIGINT - The batch identifier for the staging data to publish (must exist in [Data].[stg_DistributorInventory]).
    @snapshot_date DATE - The snapshot date to assign to published records. Only records with as_of_datetime equal to today's date (CAST(GETDATE() AS DATE)) are included in the aggregation.
Returns: A resultset with columns: inserted_count, updated_count, total_count (one row summary).
How to run: Execute via EXEC [Data].[etl_usp_build_distributor_inventory_snapshot] @batch_id = 123, @snapshot_date = '2024-01-15'.
*/

CREATE OR ALTER PROCEDURE [Data].[etl_usp_build_distributor_inventory_snapshot]
    @batch_id BIGINT,
    @snapshot_date DATE
AS
BEGIN
    SET NOCOUNT ON;
    
    -- Validate parameters
    IF @batch_id IS NULL
    BEGIN
        THROW 50000, N'@batch_id cannot be NULL. Provide a valid batch identifier.', 1;
    END;
    
    IF @snapshot_date IS NULL
    BEGIN
        THROW 50000, N'@snapshot_date cannot be NULL. Provide a valid snapshot date.', 1;
    END;
    
    -- Table variable to capture MERGE results
    DECLARE @MergeResults TABLE (
        ActionType NVARCHAR(10),
        snapshot_date DATE,
        product_id INT,
        distributor_id INT
    );
    
    -- Get today's date for filtering staging data
    -- Only records with as_of_datetime equal to today's date are included in the snapshot
    DECLARE @today_date DATE = CAST(GETDATE() AS DATE);
    
    -- Build source dataset: aggregate staging data by (product_id, distributor_id) combination
    -- IMPORTANT: This aggregation sums inventory quantities across ALL centers for each (product_id, distributor_id) combination
    -- Grain: One row per (product_id, distributor_id) combination
    -- Aggregation rule: SUM(on_hand_qty) - sums on_hand_qty across all centers for each (product_id, distributor_id) combination
    -- Filter to only today's date (as_of_datetime = @today_date) to capture current inventory levels
    -- Filter out NULL keys to ensure snapshot grain integrity (snapshot table requires non-null product_id and distributor_id)
    WITH AggregatedStaging AS (
        SELECT 
            product_id,
            distributor_id,
            SUM(on_hand_qty) AS on_hand_qty  -- Sum across all centers for this (product_id, distributor_id) combination
        FROM [Data].[stg_DistributorInventory]
        WHERE batch_id = @batch_id
          AND product_id IS NOT NULL
          AND distributor_id IS NOT NULL
          AND as_of_datetime = @today_date  -- Only include today's inventory data
        GROUP BY product_id, distributor_id  -- Aggregate by (product_id, distributor_id) combination
    )
    -- MERGE into snapshot table
    MERGE [Data].[snp_DistributorInventorySnapshot] AS target
    USING AggregatedStaging AS source
        ON target.snapshot_date = @snapshot_date
       AND target.product_id = source.product_id
       AND target.distributor_id = source.distributor_id
    WHEN MATCHED THEN
        UPDATE SET
            on_hand_qty = source.on_hand_qty,
            batch_id = @batch_id
            -- Note: created_at is not updated to preserve original creation timestamp
    WHEN NOT MATCHED BY TARGET THEN
        INSERT (snapshot_date, product_id, distributor_id, on_hand_qty, batch_id)
        VALUES (@snapshot_date, source.product_id, source.distributor_id, source.on_hand_qty, @batch_id)
    OUTPUT 
        $action AS ActionType,
        inserted.snapshot_date,
        inserted.product_id,
        inserted.distributor_id
    INTO @MergeResults;
    
    -- Return ONE summary result set with columns: inserted_count, updated_count, total_count
    SELECT 
        SUM(CASE WHEN ActionType = N'INSERT' THEN 1 ELSE 0 END) AS inserted_count,
        SUM(CASE WHEN ActionType = N'UPDATE' THEN 1 ELSE 0 END) AS updated_count,
        COUNT(*) AS total_count
    FROM @MergeResults;
END;
GO
