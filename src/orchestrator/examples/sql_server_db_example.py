from src.orchestrator.services.sql_server_db import DBConnectionFactory

factory = DBConnectionFactory()

with factory.connection('source') as conn:
    cursor = conn.cursor()
    cursor.execute("""
    SELECT top (10)
        CAST([FkProvider] AS INT)      AS factory_id,         
        CAST([FKProduct] AS INT)      AS product_id,         
        CAST([BatchNo] AS NVARCHAR(200)) AS product_batch_no,
        CAST([FKDate] AS DATE) AS as_of_datetime,
        CAST([DQty] AS BIGINT) AS on_hand_qty   
  FROM [DWOrchid].[dbo].[FactInventory]
  """)
    for row in cursor:
        print(row)
