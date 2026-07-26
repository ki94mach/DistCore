/*
Purpose: Build distributor inventory snapshots directly from [$(source_database)].[dbo].[FactInventory].
Grain: One row per (snapshot_date, product_id, distributor_id) — aggregated across centers.
Parameters:
    @batch_id BIGINT - Audit lineage stamped on snapshot rows.
    @snapshot_date DATE - Source filter (FKDate) and snapshot key stamped on published records.
*/

CREATE OR ALTER PROCEDURE [$(prod_schema)].[etl_usp_build_distributor_inventory_snapshot]
    @batch_id BIGINT,
    @snapshot_date DATE
AS
BEGIN
    SET NOCOUNT ON;

    IF @batch_id IS NULL
        THROW 50000, N'@batch_id cannot be NULL. Provide a valid batch identifier.', 1;

    IF @snapshot_date IS NULL
        THROW 50000, N'@snapshot_date cannot be NULL. Provide a valid snapshot date.', 1;

    DECLARE @MergeResults TABLE (
        ActionType NVARCHAR(10),
        snapshot_date DATE,
        product_id INT,
        distributor_id INT
    );

    TRUNCATE TABLE [$(prod_schema)].[snp_DistributorInventorySnapshot];

    WITH AggregatedSource AS (
        SELECT
            CAST([FkDistributor] AS INT) AS distributor_id,
            CAST([FKProduct] AS INT) AS product_id,
            SUM(CAST([DQty] AS BIGINT)) AS on_hand_qty
        FROM [$(source_database)].[dbo].[FactInventory]
        WHERE [FkDistributor] IS NOT NULL
          AND [FkCenter] IS NOT NULL
          AND [FKProduct] IS NOT NULL
          AND [FKDate] = @snapshot_date
          AND [DQty] <> 0
          AND ([Status] = N'موجودي' OR [Status] = N'در راه')
        GROUP BY [FkDistributor], [FKProduct]
    )
    MERGE [$(prod_schema)].[snp_DistributorInventorySnapshot] AS target
    USING AggregatedSource AS source
        ON target.snapshot_date = @snapshot_date
       AND target.product_id = source.product_id
       AND target.distributor_id = source.distributor_id
    WHEN MATCHED THEN
        UPDATE SET
            on_hand_qty = source.on_hand_qty,
            batch_id = @batch_id
    WHEN NOT MATCHED BY TARGET THEN
        INSERT (snapshot_date, product_id, distributor_id, on_hand_qty, batch_id)
        VALUES (@snapshot_date, source.product_id, source.distributor_id, source.on_hand_qty, @batch_id)
    OUTPUT
        $action AS ActionType,
        inserted.snapshot_date,
        inserted.product_id,
        inserted.distributor_id
    INTO @MergeResults;

    SELECT
        SUM(CASE WHEN ActionType = N'INSERT' THEN 1 ELSE 0 END) AS inserted_count,
        SUM(CASE WHEN ActionType = N'UPDATE' THEN 1 ELSE 0 END) AS updated_count,
        COUNT(*) AS total_count
    FROM @MergeResults;
END;
GO
