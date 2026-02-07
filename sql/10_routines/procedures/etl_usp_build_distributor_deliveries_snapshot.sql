/*
Purpose: Build distributor deliveries snapshots from staging ([Data].[stg_DistributorDeliveries]) into the snapshot table 
        ([Data].[snp_DistributorDeliveriesSnapshot]) for a given snapshot date.
Aggregation Logic:
    - Maps staging rows to (product_id, distributor_id) via dimension tables.
    - 6-month average delivery: SUM(delivered_quantity) / COUNT(*) over all delivery records in the last 6 months
      (excluding current month). I.e. average quantity per delivery event/batch, not per month.
    - Sets flag indicating if there was any delivery in the last 6 months.
    - Includes all product-distributor combinations from staging data.
Grain: One row per (snapshot_date, product_id, distributor_id) in the snapshot table.
Assumptions: T-SQL on SQL Server; staging table [Data].[stg_DistributorDeliveries] exists (see 024_stg_distributor_deliveries.sql); 
            snapshot table [Data].[snp_DistributorDeliveriesSnapshot] exists (see 034_snap_distributor_deliveries_snapshot.sql); 
            dimension tables [Analytics_Stage].[Data].[DimProduct], [Analytics_Stage].[Data].[DimDistrbutor], and [Analytics_Stage].[Data].[DimDate] exist and are populated.
Usage: This stored procedure is typically called as part of an ETL pipeline after staging load. 
        It computes average delivery per event (SUM/COUNT) over the last 6 months and merges into the snapshot table. 
        The procedure is idempotent: re-running with the same @batch_id and @snapshot_date will update existing records if staging data has changed, 
        or leave them unchanged if data is identical.
Parameters:
    @batch_id BIGINT - The batch identifier for the staging data to publish (must exist in [Data].[stg_DistributorDeliveries]).
    @snapshot_date DATE - Gregorian snapshot date to assign to published records. Moving averages are calculated up to this date.
    @snapshot_jalali_yyyymm INT - Optional Jalali year-month (YYYYMM). If provided, it is converted to Gregorian date
        using [Analytics_Stage].[Data].[DimDate] (ShamsiYearMonth, ShamsiDay=1) and overrides @snapshot_date.
Returns: A resultset with columns: inserted_count, updated_count, total_count (one row summary).
How to run: Execute via EXEC [Data].[etl_usp_build_distributor_deliveries_snapshot] @batch_id = 123, @snapshot_date = '2024-01-15'.
             Or EXEC [Data].[etl_usp_build_distributor_deliveries_snapshot] @batch_id = 123, @snapshot_jalali_yyyymm = 140409.
*/

CREATE OR ALTER PROCEDURE [Data].[etl_usp_build_distributor_deliveries_snapshot]
    @batch_id BIGINT,
    @snapshot_date DATE,
    @snapshot_jalali_yyyymm INT = NULL
AS
BEGIN
    SET NOCOUNT ON;

    -- Validate parameters
    IF @batch_id IS NULL
    BEGIN
        THROW 50000, N'@batch_id cannot be NULL. Provide a valid batch identifier.', 1;
    END;

    IF @snapshot_date IS NULL AND @snapshot_jalali_yyyymm IS NULL
    BEGIN
        THROW 50000, N'@snapshot_date cannot be NULL unless @snapshot_jalali_yyyymm is provided.', 1;
    END;

    -- Resolve effective snapshot date (Gregorian). If Jalali YYYYMM is provided, map to DateID via DimDate.
    DECLARE @effective_snapshot_date DATE = @snapshot_date;
    IF @snapshot_jalali_yyyymm IS NOT NULL
    BEGIN
        SELECT TOP (1)
            @effective_snapshot_date = DateID
        FROM [Analytics_Stage].[Data].[DimDate]
        WHERE ShamsiDay = 1
          AND TRY_CONVERT(INT, LongShamsiYearMonth) = @snapshot_jalali_yyyymm;

        IF @effective_snapshot_date IS NULL
        BEGIN
            THROW 50000, N'Invalid @snapshot_jalali_yyyymm. No matching DateID in [Analytics_Stage].[Data].[DimDate].', 1;
        END;
    END;

    -- Table variable to capture MERGE results
    DECLARE @MergeResults TABLE (
        ActionType NVARCHAR(10),
        snapshot_date DATE,
        product_id INT,
        distributor_id INT
    );

    -- Date range for last 6 months (excluding current month)
    DECLARE @six_months_ago DATE = DATEADD(MONTH, -6, @effective_snapshot_date);
    DECLARE @snapshot_month_start DATE = DATEFROMPARTS(YEAR(@effective_snapshot_date), MONTH(@effective_snapshot_date), 1);

    -- CTE 1: Filter staging data and map to dimensions (derive delivery month from staging [month])
    WITH StagingMapped AS (
        SELECT
            dp.ID AS product_id,
            dd.ID AS distributor_id,
            ddt.DateID AS delivery_month,
            sd.delivered_quantity
        FROM [Data].[stg_DistributorDeliveries] AS sd
        INNER JOIN [Analytics_Stage].[Data].[DimProduct] AS dp
            ON dp.ProductTitle = sd.product_name
        INNER JOIN [Analytics_Stage].[Data].[DimDistrbutor] AS dd
            ON dd.DistrbutorTitle = sd.distributor_name
        INNER JOIN [Analytics_Stage].[Data].[DimDate] AS ddt
            ON ddt.ShamsiDay = 1
           AND TRY_CONVERT(INT, ddt.LongShamsiYearMonth) = sd.[month]
        WHERE sd.batch_id = @batch_id
          AND sd.product_name IS NOT NULL
          AND sd.distributor_name IS NOT NULL
          AND sd.[month] IS NOT NULL
          AND sd.delivered_quantity IS NOT NULL
          AND sd.delivered_quantity <> 0
          AND sd.receipt_status = N'رسید شده'
    ),
    -- CTE 2: Average delivery over last 6 months (excluding current month)
    -- delivered_qty_ma_6 = sum of all delivery quantities / count of delivery records (average per delivery event)
    DeliveryAverageLast6m AS (
        SELECT
            product_id,
            distributor_id,
            CAST(SUM(delivered_quantity) AS DECIMAL(18, 4)) / NULLIF(COUNT(*), 0) AS delivered_qty_ma_6
        FROM StagingMapped
        WHERE delivery_month >= @six_months_ago
          AND delivery_month < @snapshot_month_start  -- Exclude current month
        GROUP BY product_id, distributor_id
    ),
    -- CTE 3: Check if there was any delivery in the last 6 months
    DeliveryFlag AS (
        SELECT
            product_id,
            distributor_id,
            CASE 
                WHEN COUNT(*) > 0 THEN 1
                ELSE 0
            END AS has_delivery_last_6m
        FROM StagingMapped
        WHERE delivery_month >= @six_months_ago
          AND delivery_month < @snapshot_month_start  -- Exclude current month
        GROUP BY product_id, distributor_id
    ),
    -- CTE 4: Get all unique product-distributor combinations from staging
    AllProductDistributors AS (
        SELECT DISTINCT
            product_id,
            distributor_id
        FROM StagingMapped
    )
    -- MERGE into snapshot table
    MERGE [Data].[snp_DistributorDeliveriesSnapshot] AS target
    USING (
        SELECT
            apd.product_id,
            apd.distributor_id,
            ISNULL(lma.delivered_qty_ma_6, 0) AS delivered_qty_ma_6,
            ISNULL(df.has_delivery_last_6m, 0) AS has_delivery_last_6m
        FROM AllProductDistributors AS apd
        LEFT JOIN DeliveryAverageLast6m AS lma
            ON lma.product_id = apd.product_id
           AND lma.distributor_id = apd.distributor_id
        LEFT JOIN DeliveryFlag AS df
            ON df.product_id = apd.product_id
           AND df.distributor_id = apd.distributor_id
    ) AS source
        ON target.snapshot_date = @effective_snapshot_date
       AND target.product_id = source.product_id
       AND target.distributor_id = source.distributor_id
    WHEN MATCHED THEN
        UPDATE SET
            delivered_qty_ma_6 = source.delivered_qty_ma_6,
            has_delivery_last_6m = source.has_delivery_last_6m,
            batch_id = @batch_id
    WHEN NOT MATCHED BY TARGET THEN
        INSERT (snapshot_date, product_id, distributor_id, delivered_qty_ma_6, has_delivery_last_6m, batch_id)
        VALUES (@effective_snapshot_date, source.product_id, source.distributor_id, source.delivered_qty_ma_6, source.has_delivery_last_6m, @batch_id)
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

