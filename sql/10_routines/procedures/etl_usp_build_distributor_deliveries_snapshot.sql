/*
Purpose: Build distributor deliveries snapshots from [$(prod_schema)].[fact_DistributorDeliveries] into the snapshot table 
        ([$(prod_schema)].[snp_DistributorDeliveriesSnapshot]) for a given snapshot date.
Data sources:
    - Staging [month]: Jalali YYYYMM of the *requested delivery* month (per row). Used only to decide which delivery
      records fall inside the 6-month window. Must not be used as the "current" snapshot month.
    - Current Jalali YYYYMM (snapshot month): Comes from @snapshot_jalali_yyyymm or from [$(source_database)].[$(source_schema)].[DimDate]
      via @effective_snapshot_date; never from staging.
Aggregation Logic:
    - Maps fact rows to (product_id, distributor_id) via dimension tables.
    - DelMA6 = average of *monthly* delivery totals over the last 6 Jalali months (including current):
      for each (product, distributor, month) SUM(qty), then AVG of those monthly sums. Matches optimizer
      docs (monthly moving average of historical deliveries), not average per delivery event.
    - Window is [current Jalali month - 5, current Jalali month]; inclusion uses fact [month] as YYYYMM.
    - Sets flag indicating if there was any delivery in the last 6 months.
    - Snapshot grain is pairs with activity in the 6-month window.
Grain: One row per (snapshot_date, product_id, distributor_id) in the snapshot table.
Assumptions: T-SQL on SQL Server; fact table [$(prod_schema)].[fact_DistributorDeliveries] exists (see 036_fact_distributor_deliveries.sql);
            snapshot table [$(prod_schema)].[snp_DistributorDeliveriesSnapshot] exists (see 034_snap_distributor_deliveries_snapshot.sql);
            dimension tables [$(source_database)].[$(source_schema)].[DimProduct], [$(source_database)].[$(source_schema)].[DimDistrbutor], and [$(source_database)].[$(source_schema)].[DimDate] exist and are populated.
Usage: This stored procedure is typically called as part of an ETL pipeline after staging load. 
        It clears the snapshot table (latest-only), then computes average delivery per event (SUM/COUNT) over the last 6 months and merges into the snapshot table. 
        The procedure is idempotent: re-running with the same @batch_id and @snapshot_date will replace the snapshot data.
Parameters:
    @batch_id BIGINT - The batch identifier stamped on published snapshot rows. Staging is read in full (all rows).
    @snapshot_date DATE - Gregorian snapshot date to assign to published records. Moving averages are calculated up to this date.
    @snapshot_jalali_yyyymm INT - Optional Jalali year-month (YYYYMM) for the *current/snapshot* month. If provided, it is
        converted to Gregorian date using [$(source_database)].[$(source_schema)].[DimDate] (ShamsiDay=1) and overrides @snapshot_date.
        This is the authoritative source for "current" Jalali month when provided.
Returns: A resultset with columns: inserted_count, updated_count, total_count (one row summary).
How to run: EXEC [$(prod_schema)].[etl_usp_build_distributor_deliveries_snapshot] @batch_id = 123, @snapshot_jalali_yyyymm = 140410;
             Or EXEC [$(prod_schema)].[etl_usp_build_distributor_deliveries_snapshot] @batch_id = 123, @snapshot_date = '2025-01-15'.
*/

CREATE OR ALTER PROCEDURE [$(prod_schema)].[etl_usp_build_distributor_deliveries_snapshot]
    @batch_id BIGINT,
    @snapshot_date DATE,
    @snapshot_jalali_yyyymm INT = NULL
AS
BEGIN
    SET NOCOUNT ON;

    IF @batch_id IS NULL
        THROW 50000, N'@batch_id cannot be NULL. Provide a valid batch identifier.', 1;

    IF @snapshot_date IS NULL AND @snapshot_jalali_yyyymm IS NULL
        THROW 50000, N'@snapshot_date cannot be NULL unless @snapshot_jalali_yyyymm is provided.', 1;

    DECLARE @effective_snapshot_date DATE = @snapshot_date;
    IF @snapshot_jalali_yyyymm IS NOT NULL
    BEGIN
        DECLARE @param_yyyymm INT = @snapshot_jalali_yyyymm;
        IF @param_yyyymm >= 1000000
            SET @param_yyyymm = @param_yyyymm / 100;

        SELECT TOP (1)
            @effective_snapshot_date = DateID
        FROM [$(source_database)].[dbo].[DimDate]
        WHERE ShamsiDay = 1
          AND (
                CASE
                    WHEN TRY_CONVERT(INT, LongShamsiYearMonth) >= 1000000
                        THEN TRY_CONVERT(INT, LongShamsiYearMonth) / 100
                    ELSE TRY_CONVERT(INT, LongShamsiYearMonth)
                END
              ) = @param_yyyymm;

        IF @effective_snapshot_date IS NULL
        BEGIN
            THROW 50000, N'Invalid @snapshot_jalali_yyyymm. No matching DateID in [$(source_database)].[$(source_schema)].[DimDate].', 1;
        END;
    END;

    DECLARE @snapshot_jalali_yyyymm_resolved INT = @snapshot_jalali_yyyymm;
    IF @snapshot_jalali_yyyymm_resolved IS NOT NULL AND @snapshot_jalali_yyyymm_resolved >= 1000000
        SET @snapshot_jalali_yyyymm_resolved = @snapshot_jalali_yyyymm_resolved / 100;

    IF @snapshot_jalali_yyyymm_resolved IS NULL
    BEGIN
        SELECT TOP (1)
            @snapshot_jalali_yyyymm_resolved = TRY_CONVERT(INT, LongShamsiYearMonth)
        FROM [$(source_database)].[dbo].[DimDate]
        WHERE DateID = @effective_snapshot_date;

        IF @snapshot_jalali_yyyymm_resolved IS NOT NULL AND @snapshot_jalali_yyyymm_resolved >= 1000000
            SET @snapshot_jalali_yyyymm_resolved = @snapshot_jalali_yyyymm_resolved / 100;

        IF @snapshot_jalali_yyyymm_resolved IS NULL
            THROW 50000, N'Snapshot date not found in [$(source_database)].[$(source_schema)].[DimDate]. Cannot resolve Jalali year-month for 6-month window.', 1;
    END;

    DECLARE @y INT = @snapshot_jalali_yyyymm_resolved / 100;
    DECLARE @m INT = @snapshot_jalali_yyyymm_resolved % 100;
    SET @m = @m - 5;
    IF @m < 1 BEGIN SET @m = @m + 12; SET @y = @y - 1; END;
    DECLARE @six_months_back_jalali INT = @y * 100 + @m;

    DECLARE @MergeResults TABLE (
        ActionType NVARCHAR(10),
        snapshot_date DATE,
        product_id INT,
        distributor_id INT
    );

    -- Clear snapshot table (latest-only) before reloading
    TRUNCATE TABLE [$(prod_schema)].[snp_DistributorDeliveriesSnapshot];

    WITH FactMapped AS (
        SELECT
            dp.ID AS product_id,
            dd.ID AS distributor_id,
            CASE
                WHEN sd.[month] >= 1000000 THEN sd.[month] / 100
                ELSE sd.[month]
            END AS delivery_jalali_yyyymm,
            sd.delivered_quantity
        FROM [$(prod_schema)].[fact_DistributorDeliveries] AS sd
        INNER JOIN [$(source_database)].[$(source_schema)].[DimProduct] AS dp
            ON dp.ProductTitle = sd.product_name
        INNER JOIN [$(source_database)].[$(source_schema)].[DimDistrbutor] AS dd
            ON dd.DistrbutorTitle = sd.distributor_name
        WHERE sd.product_name IS NOT NULL
          AND sd.distributor_name IS NOT NULL
          AND sd.[month] IS NOT NULL
          AND sd.delivered_quantity IS NOT NULL
          AND sd.delivered_quantity <> 0
          AND sd.receipt_status = N'رسید شده'
          AND (
                CASE
                    WHEN sd.[month] >= 1000000 THEN sd.[month] / 100
                    ELSE sd.[month]
                END
              ) >= 100000  -- require Jalali YYYYMM (not bare month 1-12)
    ),
    FactInWindow AS (
        SELECT
            product_id,
            distributor_id,
            delivery_jalali_yyyymm,
            delivered_quantity
        FROM FactMapped
        WHERE delivery_jalali_yyyymm >= @six_months_back_jalali
          AND delivery_jalali_yyyymm <= @snapshot_jalali_yyyymm_resolved
    ),
    MonthlyTotals AS (
        SELECT
            product_id,
            distributor_id,
            delivery_jalali_yyyymm,
            SUM(CAST(delivered_quantity AS DECIMAL(18, 4))) AS monthly_qty
        FROM FactInWindow
        GROUP BY product_id, distributor_id, delivery_jalali_yyyymm
    ),
    -- DelMA6 = average of monthly delivery totals over months with activity in the window
    DeliveryAverageLast6m AS (
        SELECT
            product_id,
            distributor_id,
            AVG(monthly_qty) AS delivered_qty_ma_6
        FROM MonthlyTotals
        GROUP BY product_id, distributor_id
    ),
    DeliveryFlag AS (
        SELECT
            product_id,
            distributor_id,
            CAST(1 AS BIT) AS has_delivery_last_6m
        FROM FactInWindow
        GROUP BY product_id, distributor_id
    )
    -- MERGE into snapshot table
    MERGE [$(prod_schema)].[snp_DistributorDeliveriesSnapshot] AS target
    USING (
        SELECT
            lma.product_id,
            lma.distributor_id,
            lma.delivered_qty_ma_6,
            ISNULL(df.has_delivery_last_6m, 0) AS has_delivery_last_6m
        FROM DeliveryAverageLast6m AS lma
        LEFT JOIN DeliveryFlag AS df
            ON df.product_id = lma.product_id
           AND df.distributor_id = lma.distributor_id
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

    SELECT
        SUM(CASE WHEN ActionType = N'INSERT' THEN 1 ELSE 0 END) AS inserted_count,
        SUM(CASE WHEN ActionType = N'UPDATE' THEN 1 ELSE 0 END) AS updated_count,
        COUNT(*) AS total_count
    FROM @MergeResults;
END;
GO
