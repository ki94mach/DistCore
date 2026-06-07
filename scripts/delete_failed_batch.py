# In your Python script or terminal
import sys
from pathlib import Path

# Add project root to Python path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.orchestrator.pipelines.factory_inventory import FactoryInventoryPipeline
from src.orchestrator.services.vpn import ensure_vpn_connected

# SQL Server is behind the corporate VPN — make sure it is up.
ensure_vpn_connected()

YOUR_BATCH_ID = [1, 2, 3, 4]
for batch_id in range(17):
    pipeline = FactoryInventoryPipeline(batch_id=batch_id)
    # Finish the batch as FAILED
    pipeline.finish_batch(batch_id, 'FAILED', 'Process interrupted by user')
    print(f"Batch {batch_id} finished as FAILED")