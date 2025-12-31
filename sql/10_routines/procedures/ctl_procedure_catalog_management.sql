/*
Purpose: Create stored procedures for managing the procedure catalog (register, update, enable/disable, log executions).
Assumptions: T-SQL on SQL Server; [Data] schema and procedure catalog tables exist (see 060_procedure_catalog.sql); requires permissions to create procedures and insert/update on catalog tables.
Usage: These procedures provide a standardized way to manage procedure metadata and track executions.
How to run: Execute in SSMS or via sqlcmd against the target database; script is idempotent using CREATE OR ALTER.
*/

-- =============================================
-- Procedure: [Data].[ctl_usp_register_procedure]
-- Purpose: Register or update a procedure in the catalog
-- =============================================
CREATE OR ALTER PROCEDURE [Data].[ctl_usp_register_procedure]
    @procedure_name NVARCHAR(200),
    @schema_name NVARCHAR(128) = N'Data',
    @procedure_category NVARCHAR(50),
    @description NVARCHAR(1000) = NULL,
    @purpose NVARCHAR(MAX) = NULL,
    @version NVARCHAR(20) = NULL,
    @is_enabled BIT = 1,
    @created_by NVARCHAR(100) = NULL,
    @notes NVARCHAR(MAX) = NULL
AS
BEGIN
    SET NOCOUNT ON;
    
    BEGIN TRY
        -- Validate required parameters
        IF @procedure_name IS NULL OR LEN(LTRIM(RTRIM(@procedure_name))) = 0
        BEGIN
            THROW 50000, N'@procedure_name cannot be NULL or empty', 1;
        END;
        
        IF @procedure_category IS NULL OR LEN(LTRIM(RTRIM(@procedure_category))) = 0
        BEGIN
            THROW 50000, N'@procedure_category cannot be NULL or empty', 1;
        END;
        
        -- Upsert procedure catalog entry
        MERGE [Data].[ctl_ProcedureCatalog] AS target
        USING (SELECT 
            @procedure_name AS procedure_name,
            @schema_name AS schema_name,
            @procedure_category AS procedure_category,
            @description AS description,
            @purpose AS purpose,
            @is_enabled AS is_enabled,
            @version AS version,
            @created_by AS created_by,
            @notes AS notes
        ) AS source
        ON target.procedure_name = source.procedure_name
        WHEN MATCHED THEN
            UPDATE SET
                schema_name = source.schema_name,
                procedure_category = source.procedure_category,
                description = source.description,
                purpose = source.purpose,
                is_enabled = source.is_enabled,
                version = source.version,
                updated_at = SYSUTCDATETIME(),
                notes = source.notes
        WHEN NOT MATCHED BY TARGET THEN
            INSERT (procedure_name, schema_name, procedure_category, description, purpose, is_enabled, version, created_by, notes)
            VALUES (source.procedure_name, source.schema_name, source.procedure_category, source.description, source.purpose, source.is_enabled, source.version, source.created_by, source.notes);
        
        SELECT @procedure_name AS procedure_name, 
               CASE WHEN @@ROWCOUNT > 0 THEN N'Registered/Updated successfully' ELSE N'No changes' END AS result;
        
    END TRY
    BEGIN CATCH
        THROW;
    END CATCH;
END;
GO

-- =============================================
-- Procedure: [Data].[ctl_usp_register_procedure_parameter]
-- Purpose: Register or update a parameter for a procedure
-- =============================================
CREATE OR ALTER PROCEDURE [Data].[ctl_usp_register_procedure_parameter]
    @procedure_name NVARCHAR(200),
    @parameter_name NVARCHAR(128),
    @parameter_type NVARCHAR(50), -- 'INPUT', 'OUTPUT', 'INPUT_OUTPUT'
    @sql_data_type NVARCHAR(128) = NULL,
    @is_required BIT = 1,
    @default_value NVARCHAR(500) = NULL,
    @description NVARCHAR(1000) = NULL,
    @ordinal_position INT
AS
BEGIN
    SET NOCOUNT ON;
    
    BEGIN TRY
        -- Validate required parameters
        IF @procedure_name IS NULL OR LEN(LTRIM(RTRIM(@procedure_name))) = 0
        BEGIN
            THROW 50000, N'@procedure_name cannot be NULL or empty', 1;
        END;
        
        IF @parameter_name IS NULL OR LEN(LTRIM(RTRIM(@parameter_name))) = 0
        BEGIN
            THROW 50000, N'@parameter_name cannot be NULL or empty', 1;
        END;
        
        -- Remove @ prefix if present
        SET @parameter_name = LTRIM(RTRIM(REPLACE(@parameter_name, '@', '')));
        
        -- Validate procedure exists
        IF NOT EXISTS (SELECT 1 FROM [Data].[ctl_ProcedureCatalog] WHERE procedure_name = @procedure_name)
        BEGIN
            DECLARE @error_msg1 NVARCHAR(4000) = N'Procedure ' + @procedure_name + N' does not exist in catalog. Register procedure first.';
            THROW 50000, @error_msg1, 1;
        END;
        
        -- Upsert parameter
        MERGE [Data].[ctl_ProcedureParameter] AS target
        USING (SELECT 
            @procedure_name AS procedure_name,
            @parameter_name AS parameter_name,
            @parameter_type AS parameter_type,
            @sql_data_type AS sql_data_type,
            @is_required AS is_required,
            @default_value AS default_value,
            @description AS description,
            @ordinal_position AS ordinal_position
        ) AS source
        ON target.procedure_name = source.procedure_name AND target.parameter_name = source.parameter_name
        WHEN MATCHED THEN
            UPDATE SET
                parameter_type = source.parameter_type,
                sql_data_type = source.sql_data_type,
                is_required = source.is_required,
                default_value = source.default_value,
                description = source.description,
                ordinal_position = source.ordinal_position
        WHEN NOT MATCHED BY TARGET THEN
            INSERT (procedure_name, parameter_name, parameter_type, sql_data_type, is_required, default_value, description, ordinal_position)
            VALUES (source.procedure_name, source.parameter_name, source.parameter_type, source.sql_data_type, source.is_required, source.default_value, source.description, source.ordinal_position);
        
        SELECT @procedure_name AS procedure_name, 
               @parameter_name AS parameter_name,
               CASE WHEN @@ROWCOUNT > 0 THEN N'Registered/Updated successfully' ELSE N'No changes' END AS result;
        
    END TRY
    BEGIN CATCH
        THROW;
    END CATCH;
END;
GO

-- =============================================
-- Procedure: [Data].[ctl_usp_log_procedure_execution]
-- Purpose: Log a procedure execution (start or finish)
-- =============================================
CREATE OR ALTER PROCEDURE [Data].[ctl_usp_log_procedure_execution]
    @procedure_name NVARCHAR(200),
    @execution_id BIGINT = NULL OUTPUT, -- If NULL, creates new; if provided, updates existing
    @batch_id BIGINT = NULL,
    @status NVARCHAR(20) = N'RUNNING', -- RUNNING/SUCCESS/FAILED
    @error_message NVARCHAR(4000) = NULL,
    @parameters_json NVARCHAR(MAX) = NULL,
    @result_count INT = NULL,
    @triggered_by NVARCHAR(100) = NULL
AS
BEGIN
    SET NOCOUNT ON;
    
    BEGIN TRY
        -- Validate required parameters
        IF @procedure_name IS NULL OR LEN(LTRIM(RTRIM(@procedure_name))) = 0
        BEGIN
            THROW 50000, N'@procedure_name cannot be NULL or empty', 1;
        END;
        
        -- If execution_id is NULL, create new execution record
        IF @execution_id IS NULL
        BEGIN
            INSERT INTO [Data].[ctl_ProcedureExecution] (
                procedure_name,
                batch_id,
                started_at,
                status,
                error_message,
                parameters_json,
                result_count,
                triggered_by
            )
            VALUES (
                @procedure_name,
                @batch_id,
                SYSUTCDATETIME(),
                @status,
                @error_message,
                @parameters_json,
                @result_count,
                @triggered_by
            );
            
            SET @execution_id = SCOPE_IDENTITY();
        END
        ELSE
        BEGIN
            -- Update existing execution record
            DECLARE @started_at DATETIME2;
            SELECT @started_at = started_at 
            FROM [Data].[ctl_ProcedureExecution] 
            WHERE execution_id = @execution_id;
            
            IF @started_at IS NULL
            BEGIN
                DECLARE @error_msg2 NVARCHAR(4000) = N'Execution ID ' + CAST(@execution_id AS NVARCHAR(20)) + N' does not exist';
                THROW 50000, @error_msg2, 1;
            END;
            
            DECLARE @duration_ms INT = DATEDIFF(MILLISECOND, @started_at, SYSUTCDATETIME());
            
            UPDATE [Data].[ctl_ProcedureExecution]
            SET finished_at = SYSUTCDATETIME(),
                duration_ms = @duration_ms,
                status = @status,
                error_message = @error_message,
                result_count = @result_count
            WHERE execution_id = @execution_id;
        END;
        
        SELECT @execution_id AS execution_id, @procedure_name AS procedure_name, @status AS status;
        
    END TRY
    BEGIN CATCH
        THROW;
    END CATCH;
END;
GO

-- =============================================
-- Procedure: [Data].[ctl_usp_get_procedure_info]
-- Purpose: Get detailed information about a procedure including parameters
-- =============================================
CREATE OR ALTER PROCEDURE [Data].[ctl_usp_get_procedure_info]
    @procedure_name NVARCHAR(200)
AS
BEGIN
    SET NOCOUNT ON;
    
    BEGIN TRY
        -- Return procedure catalog info
        SELECT 
            pc.procedure_name,
            pc.schema_name,
            pc.procedure_category,
            pc.description,
            pc.purpose,
            pc.is_enabled,
            pc.version,
            pc.created_at,
            pc.updated_at,
            pc.created_by,
            pc.notes
        FROM [Data].[ctl_ProcedureCatalog] pc
        WHERE pc.procedure_name = @procedure_name;
        
        -- Return parameters
        SELECT 
            pp.parameter_name,
            pp.parameter_type,
            pp.sql_data_type,
            pp.is_required,
            pp.default_value,
            pp.description,
            pp.ordinal_position
        FROM [Data].[ctl_ProcedureParameter] pp
        WHERE pp.procedure_name = @procedure_name
        ORDER BY pp.ordinal_position;
        
        -- Return recent execution history (last 10)
        SELECT TOP 10
            pe.execution_id,
            pe.batch_id,
            pe.started_at,
            pe.finished_at,
            pe.duration_ms,
            pe.status,
            pe.error_message,
            pe.result_count,
            pe.triggered_by
        FROM [Data].[ctl_ProcedureExecution] pe
        WHERE pe.procedure_name = @procedure_name
        ORDER BY pe.started_at DESC;
        
    END TRY
    BEGIN CATCH
        THROW;
    END CATCH;
END;
GO

-- =============================================
-- Procedure: [Data].[ctl_usp_list_procedures]
-- Purpose: List procedures with optional filtering
-- =============================================
CREATE OR ALTER PROCEDURE [Data].[ctl_usp_list_procedures]
    @procedure_category NVARCHAR(50) = NULL,
    @is_enabled BIT = NULL,
    @search_term NVARCHAR(200) = NULL
AS
BEGIN
    SET NOCOUNT ON;
    
    BEGIN TRY
        SELECT 
            pc.procedure_name,
            pc.schema_name,
            pc.procedure_category,
            pc.description,
            pc.is_enabled,
            pc.version,
            COUNT(pp.parameter_id) AS parameter_count,
            pc.created_at,
            pc.updated_at
        FROM [Data].[ctl_ProcedureCatalog] pc
        LEFT JOIN [Data].[ctl_ProcedureParameter] pp ON pc.procedure_name = pp.procedure_name
        WHERE (@procedure_category IS NULL OR pc.procedure_category = @procedure_category)
          AND (@is_enabled IS NULL OR pc.is_enabled = @is_enabled)
          AND (@search_term IS NULL OR pc.procedure_name LIKE N'%' + @search_term + N'%' OR pc.description LIKE N'%' + @search_term + N'%')
        GROUP BY pc.procedure_name, pc.schema_name, pc.procedure_category, pc.description, pc.is_enabled, pc.version, pc.created_at, pc.updated_at
        ORDER BY pc.procedure_category, pc.procedure_name;
        
    END TRY
    BEGIN CATCH
        THROW;
    END CATCH;
END;
GO

/*
Example Usage:

-- Example 1: Register a new procedure
EXEC [Data].[ctl_usp_register_procedure]
    @procedure_name = N'[Data].[etl_usp_load_stage_factory_inventory]',
    @schema_name = N'Data',
    @procedure_category = N'ETL',
    @description = N'Load factory inventory data into staging table',
    @purpose = N'Extracts factory inventory data from source and loads into [Data].[stg_FactoryInventory] staging table',
    @version = N'1.0.0',
    @is_enabled = 1,
    @created_by = N'SYSTEM';

-- Example 2: Register procedure parameters
EXEC [Data].[ctl_usp_register_procedure_parameter]
    @procedure_name = N'[Data].[etl_usp_load_stage_factory_inventory]',
    @parameter_name = N'batch_id',
    @parameter_type = N'INPUT',
    @sql_data_type = N'BIGINT',
    @is_required = 1,
    @description = N'Batch ID for this load operation',
    @ordinal_position = 1;

-- Example 3: Log procedure execution start
DECLARE @ExecId BIGINT;
EXEC [Data].[ctl_usp_log_procedure_execution]
    @procedure_name = N'[Data].[etl_usp_run_factory_inventory_pipeline]',
    @execution_id = @ExecId OUTPUT,
    @batch_id = 123,
    @status = N'RUNNING',
    @triggered_by = N'SCHEDULED_JOB';

-- Example 4: Log procedure execution finish
EXEC [Data].[ctl_usp_log_procedure_execution]
    @procedure_name = N'[Data].[etl_usp_run_factory_inventory_pipeline]',
    @execution_id = @ExecId, -- Use the execution_id from step 3
    @status = N'SUCCESS',
    @result_count = 1500;

-- Example 5: Get procedure information
EXEC [Data].[ctl_usp_get_procedure_info]
    @procedure_name = N'[Data].[etl_usp_run_factory_inventory_pipeline]';

-- Example 6: List all ETL procedures
EXEC [Data].[ctl_usp_list_procedures]
    @procedure_category = N'ETL',
    @is_enabled = 1;

-- Example 7: Search procedures
EXEC [Data].[ctl_usp_list_procedures]
    @search_term = N'factory_inventory';
*/

