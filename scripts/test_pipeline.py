"""Manual test script for FactoryInventoryPipeline."""

import sys
from pathlib import Path
from datetime import date

# Add project root to Python path so 'src' module can be found
# Get the absolute path of this script
_current_file = Path(__file__).resolve()
# This script is in scripts/, so parent.parent gets us to project root
_project_root = _current_file.parent.parent

# Add to sys.path if not already there
_project_root_str = str(_project_root)
if _project_root_str not in sys.path:
    sys.path.insert(0, _project_root_str)

# Verify we can find src directory
_src_dir = _project_root / 'src'
if not _src_dir.exists():
    raise RuntimeError(
        f"Cannot find 'src' directory at {_src_dir}. "
        f"Project root resolved to: {_project_root}"
    )

from src.orchestrator.pipelines.factory_inventory import FactoryInventoryPipeline


def main():
    """Run manual test of the pipeline."""
    print("=" * 60)
    print("Factory Inventory Pipeline Test")
    print("=" * 60)
    
    # Configuration
    batch_id = int(input("Enter batch ID (or press Enter for 999): ") or "999")
    snapshot_date_str = input("Enter snapshot date (YYYY-MM-DD) or press Enter for today: ")
    
    if snapshot_date_str:
        year, month, day = map(int, snapshot_date_str.split('-'))
        snapshot_date = date(year, month, day)
    else:
        from datetime import date as dt_date
        snapshot_date = dt_date.today()
    
    print(f"\nRunning pipeline with:")
    print(f"  Batch ID: {batch_id}")
    print(f"  Snapshot Date: {snapshot_date}")
    print("-" * 60)
    
    try:
        # Create pipeline
        pipeline = FactoryInventoryPipeline(
            batch_id=batch_id,
            snapshot_date=snapshot_date
        )
        
        print("\n1. Testing individual stages...")
        
        # Test load_stage
        print("\n   → Loading stage...")
        pipeline.load_stage()
        print("   ✓ Load stage completed")
        
        # Test validate
        print("\n   → Validating...")
        pipeline.validate()
        print("   ✓ Validation completed")
        
        # Test publish
        print("\n   → Publishing...")
        pipeline.publish()
        print("   ✓ Publish completed")
        
        print("\n" + "=" * 60)
        print("All stages completed successfully!")
        print("=" * 60)
        
        # Option to run full pipeline
        run_full = input("\nRun full pipeline (y/n)? ").lower() == 'y'
        if run_full:
            print("\n2. Running full pipeline...")
            pipeline.run()
            print("   ✓ Full pipeline completed successfully!")
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()

