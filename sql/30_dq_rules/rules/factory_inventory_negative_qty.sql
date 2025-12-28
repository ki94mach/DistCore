/*
Purpose: Data quality rule to check for negative on_hand_qty values in [Data].[stg_FactoryInventory] for a given batch.
Assumptions: T-SQL on SQL Server; staging table [Data].[stg_FactoryInventory] exists (see 020_stg_factory_inventory.sql); @batch_id corresponds to rows loaded in staging.
Usage: This rule validates that on_hand_qty is not negative. Negative quantities may indicate data quality issues, backorders, or other business conditions that should be flagged. Returns the count of failed rows and a sample of up to 50 failing records.
Parameters:
    @batch_id BIGINT - The batch identifier to validate (must match rows in [Data].[stg_FactoryInventory]).
How to run: Execute in SSMS or via sqlcmd. Set @batch_id parameter and execute. Returns failed_count and sample rows.
*/

DECLARE @batch_id BIGINT = NULL;  -- TODO: Set this parameter when calling

-- Validate @batch_id is provided
IF @batch_id IS NULL
BEGIN
    RAISERROR('@batch_id cannot be NULL. Provide a valid batch identifier.', 16, 1);
    RETURN;
END;

-- Return failed count
SELECT 
    COUNT(*) AS failed_count
FROM [Data].[stg_FactoryInventory]
WHERE batch_id = @batch_id
  AND on_hand_qty < 0;

-- Return sample of up to 50 failing rows
SELECT TOP 50
    batch_id,
    factory_id,
    product_id,
    product_batch_no,
    as_of_datetime,
    on_hand_qty,
    ingested_at
FROM [Data].[stg_FactoryInventory]
WHERE batch_id = @batch_id
  AND on_hand_qty < 0
ORDER BY factory_id, product_id, product_batch_no;

/*
Example Execution:

-- Example 1: Check for negative quantities in batch 123
DECLARE @batch_id BIGINT = 123;
-- Then execute the entire script

-- Example 2: Verify all rows in a batch
SELECT 
    batch_id,
    factory_id,
    product_id,
    product_batch_no,
    on_hand_qty,
    CASE 
        WHEN on_hand_qty < 0 THEN 'NEGATIVE'
        WHEN on_hand_qty = 0 THEN 'ZERO'
        ELSE 'POSITIVE'
    END AS qty_status
FROM [Data].[stg_FactoryInventory]
WHERE batch_id = 123
ORDER BY on_hand_qty, factory_id, product_id, product_batch_no;
*/
