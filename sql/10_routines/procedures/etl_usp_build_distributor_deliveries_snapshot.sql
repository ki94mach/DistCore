/*
Purpose: Build distributor deliveries snapshots from [Data].[fact_DistributorDeliveries] into the snapshot table 
        ([Data].[snp_DistributorDeliveriesSnapshot]) for a given snapshot date.
Data sources:
    - Staging [month]: Jalali YYYYMM of the *requested delivery* month (per row). Used only to decide which delivery
      records fall inside the 6-month window. Must not be used as the "current" snapshot month.
    - Current Jalali YYYYMM (snapshot month): Comes from @snapshot_jalali_yyyymm or from [DWOrchid].[Data].[DimDate]
      via @effective_snapshot_date; never from staging.
Aggregation Logic:
    - Maps staging rows to (product_id, distributor_id) via dimension tables.
    - 6-month average delivery: SUM(delivered_quantity) / COUNT(*) over all delivery records in the last 6 Jalali months
      (including current month). I.e. average quantity per delivery event/allocation, not per month. Window is
      [current Jalali month - 5, current Jalali month]; delivery inclusion uses staging [month].
    - Sets flag indicating if there was any delivery in the last 6 months.
    - Includes all product-distributor combinations from staging data.
Grain: One row per (snapshot_date, product_id, distributor_id) in the snapshot table.
Assumptions: T-SQL on SQL Server; fact table [Data].[fact_DistributorDeliveries] exists (see 036_fact_distributor_deliveries.sql);
            snapshot table [Data].[snp_DistributorDeliveriesSnapshot] exists (see 034_snap_distributor_deliveries_snapshot.sql);
            dimension tables [DWOrchid].[Data].[DimProduct], [DWOrchid].[Data].[DimDistrbutor], and [DWOrchid].[Data].[DimDate] exist and are populated.
Usage: This stored procedure is typically called as part of an ETL pipeline after staging load. 
        It clears the snapshot table (latest-only), then computes average delivery per event (SUM/COUNT) over the last 6 months and merges into the snapshot table. 
        The procedure is idempotent: re-running with the same @batch_id and @snapshot_date will replace the snapshot data.
Parameters:
    @batch_id BIGINT - The batch identifier stamped on published snapshot rows. Staging is read in full (all rows).
    @snapshot_date DATE - Gregorian snapshot date to assign to published records. Moving averages are calculated up to this date.
    @snapshot_jalali_yyyymm INT - Optional Jalali year-month (YYYYMM) for the *current/snapshot* month. If provided, it is
        converted to Gregorian date using [DWOrchid].[Data].[DimDate] (ShamsiDay=1) and overrides @snapshot_date.
        This is the authoritative source for "current" Jalali month when provided.
Returns: A resultset with columns: inserted_count, updated_count, total_count (one row summary).
How to run: EXEC [Data].[etl_usp_build_distributor_deliveries_snapshot] @batch_id = 123, @snapshot_jalali_yyyymm = 140410;
             Or EXEC [Data].[etl_usp_build_distributor_deliveries_snapshot] @batch_id = 123, @snapshot_date = '2025-01-15'.
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
        FROM [DWOrchid].[Data].[DimDate]
        WHERE ShamsiDay = 1
          AND TRY_CONVERT(INT, LongShamsiYearMonth) = @snapshot_jalali_yyyymm;

        IF @effective_snapshot_date IS NULL
        BEGIN
            THROW 50000, N'Invalid @snapshot_jalali_yyyymm. No matching DateID in [DWOrchid].[Data].[DimDate].', 1;
        END;
    END;

    -- Current/snapshot Jalali YYYYMM: from parameter or DimDate only (never from staging). Used as upper bound of 6-month window.
    DECLARE @snapshot_jalali_yyyymm_resolved INT = @snapshot_jalali_yyyymm;
    IF @snapshot_jalali_yyyymm_resolved IS NULL
    BEGIN
        SELECT TOP (1)
            @snapshot_jalali_yyyymm_resolved = TRY_CONVERT(INT, LongShamsiYearMonth)
        FROM [DWOrchid].[Data].[DimDate]
        WHERE DateID = @effective_snapshot_date;
        -- If LongShamsiYearMonth is YYYYMMDD (8 digits), reduce to YYYYMM
        IF @snapshot_jalali_yyyymm_resolved IS NOT NULL AND @snapshot_jalali_yyyymm_resolved >= 1000000
            SET @snapshot_jalali_yyyymm_resolved = @snapshot_jalali_yyyymm_resolved / 100;
        IF @snapshot_jalali_yyyymm_resolved IS NULL
            THROW 50000, N'Snapshot date not found in [DWOrchid].[Data].[DimDate]. Cannot resolve Jalali year-month for 6-month window.', 1;
    END;
    -- 6 months including current = current Jalali month and 5 before (Jalali arithmetic). Staging [month] = delivery month, compared to this window.
    DECLARE @y INT = @snapshot_jalali_yyyymm_resolved / 100;
    DECLARE @m INT = @snapshot_jalali_yyyymm_resolved % 100;
    SET @m = @m - 5;
    IF @m < 1 BEGIN SET @m = @m + 12; SET @y = @y - 1; END;
    DECLARE @six_months_back_jalali INT = @y * 100 + @m;

    -- Table variable to capture MERGE results
    DECLARE @MergeResults TABLE (
        ActionType NVARCHAR(10),
        snapshot_date DATE,
        product_id INT,
        distributor_id INT
    );

    -- Clear snapshot table (latest-only) before reloading
    TRUNCATE TABLE [Data].[snp_DistributorDeliveriesSnapshot];

    -- CTE 1: Staging [month] = Jalali YYYYMM of requested delivery (per row). Not the snapshot/current month.
    WITH StagingMapped AS (
        SELECT
            dp.ID AS product_id,
            dd.ID AS distributor_id,
            sd.[month] AS delivery_jalali_yyyymm,  -- month of requested delivery
            sd.delivered_quantity
        FROM [Data].[fact_DistributorDeliveries] AS sd
        INNER JOIN [DWOrchid].[Data].[DimProduct] AS dp
            ON dp.ProductTitle = sd.product_name
        INNER JOIN [DWOrchid].[Data].[DimDistrbutor] AS dd
            ON dd.DistrbutorTitle = sd.distributor_name
        WHERE sd.product_name IS NOT NULL
          AND sd.distributor_name IS NOT NULL
          AND sd.[month] IS NOT NULL
          AND sd.delivered_quantity IS NOT NULL
          AND sd.delivered_quantity <> 0
          AND sd.receipt_status = N'رسید شده'
    ),
    -- CTE 2: Average delivery over last 6 Jalali months (including current month)
    -- delivered_qty_ma_6 = sum of all delivery quantities / count of delivery records (average per delivery event/allocation)
    DeliveryAverageLast6m AS (
        SELECT
            product_id,
            distributor_id,
            CAST(SUM(delivered_quantity) AS DECIMAL(18, 4)) / NULLIF(COUNT(*), 0) AS delivered_qty_ma_6
        FROM StagingMapped
        WHERE delivery_jalali_yyyymm >= @six_months_back_jalali
          AND delivery_jalali_yyyymm <= @snapshot_jalali_yyyymm_resolved  -- Include current Jalali month
        GROUP BY product_id, distributor_id
    ),
    -- CTE 3: Check if there was any delivery in the last 6 Jalali months (including current month)
    DeliveryFlag AS (
        SELECT
            product_id,
            distributor_id,
            CASE 
                WHEN COUNT(*) > 0 THEN 1
                ELSE 0
            END AS has_delivery_last_6m
        FROM StagingMapped
        WHERE delivery_jalali_yyyymm >= @six_months_back_jalali
          AND delivery_jalali_yyyymm <= @snapshot_jalali_yyyymm_resolved  -- Include current Jalali month
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

