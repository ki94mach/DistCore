/*
Purpose: Extract distributor sales rows from the source table [DWOrchid].[dbo].[Flat_Fact_Sale].
Assumptions: T-SQL on SQL Server; source table [DWOrchid].[dbo].[Flat_Fact_Sale] exists and is accessible.
Usage: This query extracts sales data with specified column aliases. Can be used with incremental filtering via @since parameter.
Parameters:
    @since DATETIME2 = NULL - Optional timestamp for incremental extraction (e.g., ModifiedAt >= @since). 
                               If NULL, extracts all records.
How to run: Execute in SSMS or via sqlcmd. Can be used as part of an ETL pipeline or as a standalone query.
*/

DECLARE @since DATETIME2 = NULL;  -- Set to a specific datetime for incremental extraction, or NULL for full load



SELECT 

    [FkDistributor] AS distributor_id,
    [FKProduct] AS product_id,
    CAST([FKDate] AS DATE) AS as_of_datetime,
    SUM([DQty]) AS sales_qty
FROM 
    [DWOrchid].[dbo].[Flat_Fact_Sale]
WHERE
    [FkDistributor] IS NOT NULL
    AND [FkCenter] IS NOT NULL
    AND [FKProduct] IS NOT NULL
    AND (@since IS NULL OR [FKDate] >= @since)
    AND [DQty] <> 0
GROUP BY
    FkDistributor,
    FKProduct,
    FKDate;

