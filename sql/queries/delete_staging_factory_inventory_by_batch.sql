/*
Purpose: Delete ingested rows from staging table [$(prod_schema)].[stg_FactoryInventory] based on batch_id.
Assumptions: Run this query on the staging database (where [$(prod_schema)].[stg_FactoryInventory] exists).
Usage: 
   1. First run the PREVIEW section to see what will be deleted (commented out DELETE, shows SELECT)
   2. Review the results
   3. Uncomment the DELETE statement and comment out the SELECT to actually delete
   4. Adjust @batch_id as needed

WARNING: This operation is irreversible. Always preview before deleting!
*/

DECLARE @batch_id BIGINT = 123;  -- Replace with your batch_id

-- =============================================
-- STEP 1: PREVIEW - See what will be deleted
-- =============================================
-- Run this first to see the count and sample records that will be deleted

SELECT 
    batch_id,
    COUNT(*) AS records_to_delete,
    MIN(ingested_at) AS first_ingested,
    MAX(ingested_at) AS last_ingested,
    MIN(as_of_datetime) AS min_as_of_datetime,
    MAX(as_of_datetime) AS max_as_of_datetime
FROM [$(prod_schema)].[stg_FactoryInventory]
WHERE batch_id = @batch_id
GROUP BY batch_id;

-- Sample records that will be deleted (first 100)
SELECT TOP 100
    batch_id,
    factory_id,
    product_id,
    product_batch_no,
    as_of_datetime,
    on_hand_qty,
    ingested_at
FROM [$(prod_schema)].[stg_FactoryInventory]
WHERE batch_id = @batch_id
ORDER BY ingested_at DESC;

-- =============================================
-- STEP 2: DELETE - Uncomment to execute deletion
-- =============================================
-- WARNING: This will permanently delete records. Make sure you've reviewed the preview above!

/*
BEGIN TRANSACTION;

-- Delete records for the specified batch_id
DELETE FROM [$(prod_schema)].[stg_FactoryInventory]
WHERE batch_id = @batch_id;

-- Verify deletion (should return 0 rows)
SELECT 
    COUNT(*) AS remaining_records
FROM [$(prod_schema)].[stg_FactoryInventory]
WHERE batch_id = @batch_id;

-- Review the changes before committing
-- If everything looks correct, uncomment COMMIT
-- If something is wrong, use ROLLBACK instead
COMMIT TRANSACTION;
-- ROLLBACK TRANSACTION;  -- Use this if you need to undo the deletion
*/

-- =============================================
-- Alternative: Delete multiple batch_ids at once
-- =============================================
-- Uncomment and modify the batch_ids list as needed

/*
DECLARE @batch_ids TABLE (batch_id BIGINT);
INSERT INTO @batch_ids (batch_id) VALUES (123), (124), (125);  -- Add your batch_ids here

BEGIN TRANSACTION;

-- Preview what will be deleted
SELECT 
    batch_id,
    COUNT(*) AS records_to_delete
FROM [$(prod_schema)].[stg_FactoryInventory]
WHERE batch_id IN (SELECT batch_id FROM @batch_ids)
GROUP BY batch_id;

-- Delete records for the specified batch_ids
DELETE FROM [$(prod_schema)].[stg_FactoryInventory]
WHERE batch_id IN (SELECT batch_id FROM @batch_ids);

-- Review and commit
COMMIT TRANSACTION;
-- ROLLBACK TRANSACTION;  -- Use this if you need to undo the deletion
*/

