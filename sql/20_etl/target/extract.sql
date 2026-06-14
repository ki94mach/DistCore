/*
Purpose: Extract and aggregate target rows from the source table [$(source_database)].[dbo].[FactTarget] for the current Jalali year.
Assumptions: T-SQL on SQL Server; source table [$(source_database)].[dbo].[FactTarget] exists and is accessible.
Usage: This query extracts target data with specified column aliases, aggregates by (product_id, year, month) using SUM,
      and filters by the current Jalali year. The aggregation reduces row counts by summing TargetQuantity for each
      unique combination of product, year, and month.
Parameters:
    @since DATETIME2 = NULL - Optional timestamp for incremental extraction (not used for target, but kept for consistency).
                               Target extraction is always filtered by current Jalali year.
Note: @current_jalali_year will be substituted by Python code before execution.
      The Python pipeline calculates the Jalali year and replaces @current_jalali_year with the actual value.
How to run: Execute in SSMS or via sqlcmd. Can be used as part of an ETL pipeline or as a standalone query.
*/

-- Note: @current_jalali_year will be substituted by Python code before execution
-- The Python pipeline calculates the Jalali year and replaces @current_jalali_year with the actual value

SELECT 
    [FKProduct] AS product_id,
    [Year] AS year,
    [Month] AS month,
    Sum([TargetQuantity]) AS target_quantity
FROM 
    [$(source_database)].[dbo].[FactTarget]
WHERE
    [Year] = @current_jalali_year
    AND [FKProduct] IS NOT NULL
    AND [Year] IS NOT NULL
    AND [Month] IS NOT NULL
    AND [TargetQuantity] IS NOT NULL
GROUP BY
    [FKProduct],
    [Year],
    [Month];