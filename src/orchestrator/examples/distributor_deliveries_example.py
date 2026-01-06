"""Example usage of DistributorDeliveriesPipeline to load data from Dropbox."""

from datetime import date
from src.orchestrator.pipelines.distributor_deliveries import DistributorDeliveriesPipeline
from src.orchestrator.services.dropbox.config import DropboxConfigLoader


def main():
    """
    Example: Load distributor deliveries from Dropbox.
    
    Prerequisites:
    1. Configure Dropbox folder path in src/orchestrator/config/dropbox.yml:
       dropbox:
         distributor_deliveries_folder: /Data/Deliveries
    
    2. Store Dropbox access token using one of these methods:
       a) Windows Credential Manager (recommended):
          from src.orchestrator.services.dropbox.config import DropboxConfigLoader
          DropboxConfigLoader.store_token_in_windows_credential_manager('your_token')
       
       b) Environment variable:
          set DROPBOX_ACCESS_TOKEN=your_token
       
       c) Pass directly to pipeline (less secure)
    
    3. Ensure the Dropbox folder contains Excel files matching the pattern:
       "دیتابیس تحویل به پخش ها - [Company Name] - 1404"
    
    4. Run the staging table migration: sql/00_migrations/024_stg_distributor_deliveries.sql
    """
    
    # Initialize pipeline
    # The pipeline will automatically create a batch if batch_id is None
    # The Dropbox folder path is read from src/orchestrator/config/dropbox.yml
    pipeline = DistributorDeliveriesPipeline(
        batch_id=None,  # Will be created automatically
        snapshot_date=date.today(),  # Or specify a specific date
        # dropbox_access_token='your_token_here',  # Optional if DROPBOX_ACCESS_TOKEN env var is set
    )
    
    # Test Dropbox connection
    print("Testing Dropbox connection...")
    try:
        pipeline._dropbox_client.test_connection()
        print("✓ Dropbox connection successful")
    except Exception as e:
        print(f"✗ Dropbox connection failed: {e}")
        return
    
    # List files in Dropbox folder
    print(f"\nListing files in {pipeline._dropbox_folder_path}...")
    try:
        files = pipeline._dropbox_client.list_files(
            pipeline._dropbox_folder_path,
            pattern=r'دیتابیس تحویل به پخش ها.*\.(xlsx|xls)$'
        )
        print(f"Found {len(files)} files:")
        for file_info in files:
            print(f"  - {file_info['name']} ({file_info['size']} bytes)")
    except Exception as e:
        print(f"✗ Failed to list files: {e}")
        return
    
    # Run the complete pipeline (load_stage + publish)
    print("\nRunning pipeline...")
    try:
        pipeline.run()
        print(f"✓ Pipeline completed successfully. Batch ID: {pipeline.batch_id}")
    except Exception as e:
        print(f"✗ Pipeline failed: {e}")
        raise
    
    # Or run steps individually:
    # pipeline.load_stage(batch_size=10000)
    # pipeline.publish()


if __name__ == '__main__':
    main()

