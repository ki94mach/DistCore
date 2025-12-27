/*
Purpose: Run data quality validation checks on stg.FactoryInventory for a given batch and record results in dq.ValidationResult.
Assumptions: T-SQL on SQL Server; staging table stg.FactoryInventory exists (see 020_stg_factory_inventory.sql); validation result table dq.ValidationResult exists (see 040_dq_tables.sql); @batch_id corresponds to rows loaded in staging.
Usage: This script is typically called as part of an ETL pipeline after loading data into staging (via load_stage.sql) and before transformation. It performs critical data quality checks and fails fast if any HARD severity rules are violated, preventing bad data from propagating downstream.
Parameters:
    @batch_id BIGINT - The batch identifier to validate (must match rows in stg.FactoryInventory).
    @allow_negative BIT = 0 - If 1, allows negative on_hand_qty values (for systems where negatives are valid, e.g., backorders). If 0, treats negative quantities as validation failures.
How to run: Execute in SSMS or via sqlcmd. Should be called after load_stage.sql and before any transformation steps. The script will THROW an error if any HARD validation checks fail.
*/

DECLARE @batch_id BIGINT = NULL;  -- TODO: Set this parameter when calling
DECLARE @allow_negative BIT = 0;  -- Set to 1 if negative quantities are allowed in your business logic

-- Variables to track failures
DECLARE @total_hard_failures INT = 0;
DECLARE @check_failed_count BIGINT;
DECLARE @check_rule_name NVARCHAR(200);
DECLARE @check_sample_query NVARCHAR(MAX);

-- Validate @batch_id is provided
IF @batch_id IS NULL
BEGIN
    RAISERROR('@batch_id cannot be NULL. Provide a valid batch identifier.', 16, 1);
    RETURN;
END;

-- =============================================
-- Check 1: Null Keys
-- Validates that factory_id and product_id are not NULL
-- =============================================
SET @check_rule_name = N'FactoryInventory_NullKeys';
SET @check_sample_query = N'SELECT batch_id, factory_id, product_id, as_of_datetime, on_hand_qty FROM stg.FactoryInventory WHERE batch_id = ' + CAST(@batch_id AS NVARCHAR(20)) + N' AND (factory_id IS NULL OR product_id IS NULL)';

SELECT @check_failed_count = COUNT(*)
FROM stg.FactoryInventory
WHERE batch_id = @batch_id
  AND (factory_id IS NULL OR product_id IS NULL);

INSERT INTO dq.ValidationResult (
    batch_id,
    rule_name,
    severity,
    failed_count,
    sample_query
)
VALUES (
    @batch_id,
    @check_rule_name,
    N'HARD',
    @check_failed_count,
    @check_sample_query
);

IF @check_failed_count > 0
BEGIN
    SET @total_hard_failures = @total_hard_failures + 1;
END;

-- =============================================
-- Check 2: Negative On Hand Quantity
-- Validates that on_hand_qty is not negative (unless @allow_negative = 1)
-- =============================================
SET @check_rule_name = N'FactoryInventory_NegativeQuantity';
SET @check_sample_query = N'SELECT batch_id, factory_id, product_id, as_of_datetime, on_hand_qty FROM stg.FactoryInventory WHERE batch_id = ' + CAST(@batch_id AS NVARCHAR(20)) + N' AND on_hand_qty < 0';

IF @allow_negative = 0
BEGIN
    SELECT @check_failed_count = COUNT(*)
    FROM stg.FactoryInventory
    WHERE batch_id = @batch_id
      AND on_hand_qty < 0;
END
ELSE
BEGIN
    -- If negatives are allowed, this check always passes
    SET @check_failed_count = 0;
    SET @check_sample_query = @check_sample_query + N' -- Check skipped: @allow_negative = 1';
END;

INSERT INTO dq.ValidationResult (
    batch_id,
    rule_name,
    severity,
    failed_count,
    sample_query
)
VALUES (
    @batch_id,
    @check_rule_name,
    N'HARD',
    @check_failed_count,
    @check_sample_query
);

IF @check_failed_count > 0
BEGIN
    SET @total_hard_failures = @total_hard_failures + 1;
END;

-- =============================================
-- Check 3: Duplicate Keys
-- Validates that there are no duplicate (factory_id, product_id) combinations within this batch
-- =============================================
SET @check_rule_name = N'FactoryInventory_DuplicateKeys';
SET @check_sample_query = N'SELECT factory_id, product_id, COUNT(*) AS duplicate_count FROM stg.FactoryInventory WHERE batch_id = ' + CAST(@batch_id AS NVARCHAR(20)) + N' GROUP BY factory_id, product_id HAVING COUNT(*) > 1';

SELECT @check_failed_count = COUNT(*)
FROM (
    SELECT factory_id, product_id
    FROM stg.FactoryInventory
    WHERE batch_id = @batch_id
    GROUP BY factory_id, product_id
    HAVING COUNT(*) > 1
) AS duplicates;

INSERT INTO dq.ValidationResult (
    batch_id,
    rule_name,
    severity,
    failed_count,
    sample_query
)
VALUES (
    @batch_id,
    @check_rule_name,
    N'HARD',
    @check_failed_count,
    @check_sample_query
);

IF @check_failed_count > 0
BEGIN
    SET @total_hard_failures = @total_hard_failures + 1;
END;

-- =============================================
-- Check 4: Empty Load
-- Validates that at least one row was loaded for this batch
-- =============================================
SET @check_rule_name = N'FactoryInventory_EmptyLoad';
SET @check_sample_query = N'SELECT COUNT(*) AS row_count FROM stg.FactoryInventory WHERE batch_id = ' + CAST(@batch_id AS NVARCHAR(20));

SELECT @check_failed_count = CASE WHEN COUNT(*) = 0 THEN 1 ELSE 0 END
FROM stg.FactoryInventory
WHERE batch_id = @batch_id;

INSERT INTO dq.ValidationResult (
    batch_id,
    rule_name,
    severity,
    failed_count,
    sample_query
)
VALUES (
    @batch_id,
    @check_rule_name,
    N'HARD',
    @check_failed_count,
    @check_sample_query
);

IF @check_failed_count > 0
BEGIN
    SET @total_hard_failures = @total_hard_failures + 1;
END;

-- =============================================
-- Final Validation: Throw error if any HARD checks failed
-- =============================================
IF @total_hard_failures > 0
BEGIN
    DECLARE @error_message NVARCHAR(MAX) = N'Data quality validation failed for batch_id ' + CAST(@batch_id AS NVARCHAR(20)) + 
        N'. ' + CAST(@total_hard_failures AS NVARCHAR(10)) + 
        N' HARD severity rule(s) failed. Check dq.ValidationResult for details.';
    
    THROW 50000, @error_message, 1;
END;

-- Return summary of validation results
SELECT 
    rule_name,
    severity,
    failed_count,
    sample_query
FROM dq.ValidationResult
WHERE batch_id = @batch_id
ORDER BY rule_name;

/*
Example Execution:

-- Example 1: Validate with default settings (negative quantities not allowed)
-- Set variables at the top of this script and execute:
DECLARE @batch_id BIGINT = 123;
DECLARE @allow_negative BIT = 0;
-- Then execute the entire script

-- Example 2: Validate allowing negative quantities (for systems where negatives are valid)
DECLARE @batch_id BIGINT = 123;
DECLARE @allow_negative BIT = 1;
-- Then execute the entire script

-- Example 3: Review validation results for a batch
SELECT 
    validation_id,
    batch_id,
    rule_name,
    severity,
    failed_count,
    sample_query,
    created_at
FROM dq.ValidationResult
WHERE batch_id = 123
ORDER BY created_at DESC;

-- Example 4: Run sample query from a failed validation
-- (Copy the sample_query value from dq.ValidationResult and execute it)
-- Example output: SELECT factory_id, product_id, COUNT(*) AS duplicate_count 
--                 FROM stg.FactoryInventory WHERE batch_id = 123 
--                 GROUP BY factory_id, product_id HAVING COUNT(*) > 1;

-- Example 5: Check which validation rules failed for a batch
SELECT 
    rule_name,
    severity,
    failed_count,
    CASE 
        WHEN failed_count > 0 THEN 'FAILED'
        ELSE 'PASSED'
    END AS status
FROM dq.ValidationResult
WHERE batch_id = 123
ORDER BY 
    CASE severity 
        WHEN 'HARD' THEN 1 
        WHEN 'SOFT' THEN 2 
        ELSE 3 
    END,
    rule_name;
*/

