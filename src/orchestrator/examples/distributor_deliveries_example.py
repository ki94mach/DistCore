"""Example usage of DistributorDeliveriesPipeline to load data from DMS."""

from datetime import date

from src.orchestrator.pipelines.distributor_deliveries import DistributorDeliveriesPipeline
from src.orchestrator.services.dms.config import DmsConfigLoader


def main():
    """
    Example: Load distributor deliveries from DMS SharePoint folders.

    Prerequisites:
    1. Configure folder URLs in src/orchestrator/config/dms.yml
       (see dms.yml.example).

    2. Auth:
       - Domain-joined Windows: SSPI by default (pip install requests-negotiate-sspi)
       - Linux / Docker: NTLM via DISTCORE_DMS_USERNAME + DISTCORE_DMS_PASSWORD
         (pip install requests-ntlm)

    3. Ensure Excel files follow the pattern:
       "دیتابیس تحویل به پخش ها - [Factory Name] - 1404/1405.xlsx"

    4. Run prod migration: python scripts/migrations.py --prod
       (creates [Data].[fact_DistributorDeliveries] on the prod database)
    """
    deliveries_config = DmsConfigLoader.get_distributor_deliveries_config()

    pipeline = DistributorDeliveriesPipeline(
        batch_id=None,
        snapshot_date=date.today(),
    )

    print("Listing current-year files from DMS...")
    try:
        files = pipeline._dms_client.list_files(
            folder_url=deliveries_config['current_folder_url'],
            pattern=r'دیتابیس تحویل به پخش ها.*\.(xlsx|xls)$',
        )
        print(f"Found {len(files)} file(s) in 1405 folder.")
        for file_info in files[:5]:
            print(f"  - {file_info['name']}")
    except Exception as exc:
        print(f"Failed to list DMS files: {exc}")
        return

    print("\nRunning pipeline...")
    try:
        pipeline.run()
        print(f"Pipeline completed successfully. Batch ID: {pipeline.batch_id}")
    except Exception as exc:
        print(f"Pipeline failed: {exc}")
        raise


if __name__ == '__main__':
    main()
