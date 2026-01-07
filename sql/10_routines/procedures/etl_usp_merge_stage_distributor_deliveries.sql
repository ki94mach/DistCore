/*
Purpose: Merge a single distributor delivery row into staging table with hybrid deduplication (row_hash + business key).
Assumptions: T-SQL on SQL Server; staging table [Data].[stg_DistributorDeliveries] exists (see 024_stg_distributor_deliveries.sql).
Usage: This stored procedure is called by the Python pipeline to merge rows into staging. It implements hybrid deduplication:
   1. First checks if row_hash exists (exact duplicate) - if so, returns 'SKIP'
   2. If row_hash doesn't exist, performs MERGE on business key:
      - Primary key: warehouse_exit_letter_number (if not NULL)
      - Fallback key: product_name + distributor_name + delivery_date + batch_number
   3. Returns action taken: 'INSERT', 'UPDATE', or 'SKIP'
Parameters:
    All staging table columns as input parameters (see parameter list below)
Returns: A resultset with one row containing: action (NVARCHAR(10)) - either 'INSERT', 'UPDATE', or 'SKIP'
How to run: Called programmatically from Python pipeline. Not intended for manual execution.
*/

CREATE OR ALTER PROCEDURE [Data].[etl_usp_merge_stage_distributor_deliveries]
    @batch_id BIGINT,
    @drug_code NVARCHAR(100) = NULL,
    @product_name NVARCHAR(500) = NULL,
    @distributor_name NVARCHAR(200) = NULL,
    @batch_number NVARCHAR(200) = NULL,
    @expiry_date DATE = NULL,
    @delivered_quantity BIGINT = NULL,
    @delivered_quantity_round_up BIGINT = NULL,
    @delivered_quantity_round_down BIGINT = NULL,
    @request_date DATE = NULL,
    @delivery_date DATE = NULL,
    @month INT = NULL,
    @warehouse_exit_letter_number NVARCHAR(200) = NULL,
    @warehouse_exit_quantity BIGINT = NULL,
    @warehouse_exit_details NVARCHAR(1000) = NULL,
    @receipt_status NVARCHAR(100) = NULL,
    @release_date DATE = NULL,
    @days_between_delivery_release INT = NULL,
    @routine_delivery_quantity BIGINT = NULL,
    @supply_chain_request_quantity BIGINT = NULL,
    @factory_name NVARCHAR(200) = NULL,
    @company_name NVARCHAR(200) = NULL,
    @description NVARCHAR(1000) = NULL,
    @source_file NVARCHAR(500) = NULL,
    @row_hash VARBINARY(32) = NULL,
    @action NVARCHAR(10) OUTPUT
AS
BEGIN
    SET NOCOUNT ON;
    
    -- Step 1: Check if exact duplicate (row_hash exists)
    IF EXISTS (
        SELECT 1 
        FROM [Data].[stg_DistributorDeliveries]
        WHERE row_hash = @row_hash
    )
    BEGIN
        SET @action = 'SKIP';
        SELECT @action AS action;
        RETURN;
    END;
    
    -- Step 2: MERGE based on business key
    DECLARE @MergeResults TABLE (
        ActionType NVARCHAR(10)
    );
    
    MERGE [Data].[stg_DistributorDeliveries] AS target
    USING (
        SELECT 
            @batch_id AS batch_id,
            @drug_code AS drug_code,
            @product_name AS product_name,
            @distributor_name AS distributor_name,
            @batch_number AS batch_number,
            @expiry_date AS expiry_date,
            @delivered_quantity AS delivered_quantity,
            @delivered_quantity_round_up AS delivered_quantity_round_up,
            @delivered_quantity_round_down AS delivered_quantity_round_down,
            @request_date AS request_date,
            @delivery_date AS delivery_date,
            @month AS month,
            @warehouse_exit_letter_number AS warehouse_exit_letter_number,
            @warehouse_exit_quantity AS warehouse_exit_quantity,
            @warehouse_exit_details AS warehouse_exit_details,
            @receipt_status AS receipt_status,
            @release_date AS release_date,
            @days_between_delivery_release AS days_between_delivery_release,
            @routine_delivery_quantity AS routine_delivery_quantity,
            @supply_chain_request_quantity AS supply_chain_request_quantity,
            @factory_name AS factory_name,
            @company_name AS company_name,
            @description AS description,
            @source_file AS source_file,
            @row_hash AS row_hash
    ) AS source
    ON (
        -- Primary business key: warehouse_exit_letter_number (if both not NULL)
        (target.warehouse_exit_letter_number IS NOT NULL 
         AND source.warehouse_exit_letter_number IS NOT NULL
         AND target.warehouse_exit_letter_number = source.warehouse_exit_letter_number)
        OR
        -- Fallback business key: product + distributor + date + batch (when warehouse_exit_letter_number is NULL)
        ((target.warehouse_exit_letter_number IS NULL 
          OR source.warehouse_exit_letter_number IS NULL)
         AND target.product_name = source.product_name
         AND target.distributor_name = source.distributor_name
         AND target.delivery_date = source.delivery_date
         AND (target.batch_number = source.batch_number 
              OR (target.batch_number IS NULL AND source.batch_number IS NULL)))
    )
    WHEN MATCHED THEN
        UPDATE SET
            batch_id = source.batch_id,
            drug_code = source.drug_code,
            product_name = source.product_name,
            distributor_name = source.distributor_name,
            batch_number = source.batch_number,
            expiry_date = source.expiry_date,
            delivered_quantity = source.delivered_quantity,
            delivered_quantity_round_up = source.delivered_quantity_round_up,
            delivered_quantity_round_down = source.delivered_quantity_round_down,
            request_date = source.request_date,
            delivery_date = source.delivery_date,
            month = source.month,
            warehouse_exit_letter_number = source.warehouse_exit_letter_number,
            warehouse_exit_quantity = source.warehouse_exit_quantity,
            warehouse_exit_details = source.warehouse_exit_details,
            receipt_status = source.receipt_status,
            release_date = source.release_date,
            days_between_delivery_release = source.days_between_delivery_release,
            routine_delivery_quantity = source.routine_delivery_quantity,
            supply_chain_request_quantity = source.supply_chain_request_quantity,
            factory_name = source.factory_name,
            company_name = source.company_name,
            description = source.description,
            source_file = source.source_file,
            row_hash = source.row_hash,
            ingested_at = SYSUTCDATETIME()
    WHEN NOT MATCHED THEN
        INSERT (
            batch_id, drug_code, product_name, distributor_name, batch_number,
            expiry_date, delivered_quantity, delivered_quantity_round_up, delivered_quantity_round_down,
            request_date, delivery_date, month, warehouse_exit_letter_number, warehouse_exit_quantity,
            warehouse_exit_details, receipt_status, release_date, days_between_delivery_release,
            routine_delivery_quantity, supply_chain_request_quantity, factory_name, company_name,
            description, source_file, row_hash
        )
        VALUES (
            source.batch_id, source.drug_code, source.product_name, source.distributor_name, source.batch_number,
            source.expiry_date, source.delivered_quantity, source.delivered_quantity_round_up, source.delivered_quantity_round_down,
            source.request_date, source.delivery_date, source.month, source.warehouse_exit_letter_number, source.warehouse_exit_quantity,
            source.warehouse_exit_details, source.receipt_status, source.release_date, source.days_between_delivery_release,
            source.routine_delivery_quantity, source.supply_chain_request_quantity, source.factory_name, source.company_name,
            source.description, source.source_file, source.row_hash
        )
    OUTPUT $action INTO @MergeResults;
    
    -- Get the action and set output parameter
    SELECT @action = ActionType FROM @MergeResults;
    
    -- Ensure @action is set (should always be set, but handle NULL case)
    IF @action IS NULL
    BEGIN
        SET @action = 'INSERT';  -- Default to INSERT if somehow NULL
    END;
    
    -- Return result set
    SELECT @action AS action;
END;
GO

