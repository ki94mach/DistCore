"""Terminal access tool for ETL pipelines."""

import sys
from pathlib import Path
from datetime import date

# Add project root to Python path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.orchestrator.pipelines.factory_inventory import FactoryInventoryPipeline
from src.orchestrator.pipelines.distributor_inventory import DistributorInventoryPipeline
from src.orchestrator.pipelines.sales_snapshot import SalesSnapshotPipeline
from src.orchestrator.services.sql_server_db.factory import DBConnectionFactory
from src.orchestrator.services.sql_server_db.executors.sql_executor import SQLExecutor
from src.orchestrator.services.terminal_ui import (
    Colors,
    print_header,
    print_success,
    print_error,
    print_warning,
    print_info,
    print_action,
    print_menu_item,
    print_prompt,
    colorize
)


# Pipeline registry - easily extensible for future pipelines
PIPELINES = {
    '1': {
        'name': 'Factory Inventory',
        'class': FactoryInventoryPipeline,
        'batch_type': 'FACTORY_INVENTORY'
    },
    '2': {
        'name': 'Distributor Inventory',
        'class': DistributorInventoryPipeline,
        'batch_type': 'DISTRIBUTOR_INVENTORY'
    },
    '3': {
        'name': 'Sales Snapshot',
        'class': SalesSnapshotPipeline,
        'batch_type': 'SALES_SNAPSHOT'
    }
}


def start_new_batch(batch_type: str, triggered_by: str = 'MANUAL_TEST', database_type: str = 'test') -> int:
    """Start a new batch and return the batch_id."""
    connection_factory = DBConnectionFactory()
    sql_executor = SQLExecutor(connection_factory)
    
    result = sql_executor.execute_procedure_with_output(
        procedure_name='[Data].[ctl_usp_start_batch]',
        parameters={
            'batch_type': batch_type,
            'triggered_by': triggered_by
        },
        output_parameters=['batch_id'],
        database_type=database_type
    )
    
    batch_id = result['batch_id']
    print_success(f"Created new batch ID: {batch_id}")
    return batch_id


def select_pipeline():
    """First layer: Select a pipeline."""
    print_header("Available Pipelines", Colors.BRIGHT_CYAN)
    for key, pipeline_info in PIPELINES.items():
        print_menu_item(key, pipeline_info['name'], Colors.BRIGHT_WHITE)
    print_menu_item('q', 'Quit', Colors.BRIGHT_YELLOW)
    
    choice = print_prompt("\nSelect pipeline: ").strip().lower()
    if choice == 'q':
        return None
    return PIPELINES.get(choice)


def select_layer(pipeline_info):
    """Second layer: Select a layer/operation."""
    print_header(f"{pipeline_info['name']} - Available Layers", Colors.BRIGHT_CYAN)
    print_menu_item('1', 'Load Stage (staging layer)', Colors.BRIGHT_WHITE)
    print_menu_item('2', 'Publish (publish layer)', Colors.BRIGHT_WHITE)
    print_menu_item('3', 'Run Full Pipeline (load_stage + publish)', Colors.BRIGHT_WHITE)
    print_menu_item('b', 'Back to pipelines', Colors.BRIGHT_YELLOW)
    print_menu_item('q', 'Quit', Colors.BRIGHT_YELLOW)
    
    choice = print_prompt("\nSelect layer: ").strip().lower()
    return choice


def configure_staging(pipeline_info):
    """Configure staging layer parameters (date control)."""
    print_header("Staging Layer Configuration", Colors.BRIGHT_BLUE)
    
    # Date configuration
    print_info("\nSnapshot Date:")
    print(colorize("  - Press Enter to use today's date", Colors.DIM))
    print(colorize("  - Enter a date (YYYY-MM-DD) to use a specific date", Colors.DIM))
    snapshot_date_str = print_prompt("Enter snapshot date (YYYY-MM-DD) or press Enter for today: ").strip()
    
    snapshot_date = None
    if snapshot_date_str:
        try:
            year, month, day = map(int, snapshot_date_str.split('-'))
            snapshot_date = date(year, month, day)
        except ValueError:
            print_error("Invalid date format. Using today's date.")
            snapshot_date = None
    
    # Additional staging parameters for FactoryInventoryPipeline
    batch_size = 10000
    incremental = True
    single_date_only = False
    
    if pipeline_info['name'] == 'Factory Inventory' or pipeline_info['name'] == 'Distributor Inventory':
        print_info("\nBatch Size:")
        print(colorize("  - Press Enter for default (10000)", Colors.DIM))
        batch_size_str = print_prompt("Enter batch size (default: 10000): ").strip()
        if batch_size_str:
            try:
                batch_size = int(batch_size_str)
            except ValueError:
                print_error("Invalid batch size. Using default (10000).")
        
        print_info("\nLoad Mode:")
        print_menu_item('1', 'Incremental (load data after latest date in staging)', Colors.WHITE)
        print_menu_item('2', 'Single date only (load only snapshot_date)', Colors.WHITE)
        print_menu_item('3', 'Full load (load all data)', Colors.WHITE)
        mode_choice = print_prompt("Select mode (1/2/3, default=1): ").strip() or "1"
        
        if mode_choice == "2":
            incremental = False
            single_date_only = True
        elif mode_choice == "3":
            incremental = False
            single_date_only = False
    elif pipeline_info['name'] == 'Sales Snapshot':
        print_info("\nLoad Mode:")
        print(colorize(
            "  - Sales snapshots require single-date ingestion to scope staging.",
            Colors.DIM
        ))
        incremental = False
        single_date_only = True
    
    return {
        'snapshot_date': snapshot_date,
        'batch_size': batch_size,
        'incremental': incremental,
        'single_date_only': single_date_only
    }


def configure_publish(pipeline_info):
    """Configure publish layer parameters."""
    print_header("Publish Layer Configuration", Colors.BRIGHT_BLUE)
    
    # Date configuration (needed for publish too)
    print_info("\nSnapshot Date:")
    print(colorize("  - Press Enter to use today's date", Colors.DIM))
    print(colorize("  - Enter a date (YYYY-MM-DD) to use a specific date", Colors.DIM))
    snapshot_date_str = print_prompt("Enter snapshot date (YYYY-MM-DD) or press Enter for today: ").strip()
    
    snapshot_date = None
    if snapshot_date_str:
        try:
            year, month, day = map(int, snapshot_date_str.split('-'))
            snapshot_date = date(year, month, day)
        except ValueError:
            print_error("Invalid date format. Using today's date.")
            snapshot_date = None
    
    # Additional publish parameters can be added here for future pipelines
    publish_params = {}
    
    if pipeline_info['name'] == 'Factory Inventory' or pipeline_info['name'] == 'Distributor Inventory':
        # Currently FactoryInventoryPipeline.publish() doesn't take additional parameters
        # But we can add them here for future extensibility
        pass
    
    return {
        'snapshot_date': snapshot_date,
        **publish_params
    }


def configure_batch(pipeline_info):
    """Configure batch options."""
    print_header("Batch Configuration", Colors.BRIGHT_BLUE)
    print_menu_item('1', 'Create new batch automatically (recommended)', Colors.BRIGHT_WHITE)
    print_menu_item('2', 'Use existing batch ID', Colors.WHITE)
    print_menu_item('3', 'Let pipeline create batch automatically', Colors.WHITE)
    
    choice = print_prompt("\nSelect option (1/2/3, default=1): ").strip() or "1"
    
    batch_id = None
    if choice == "1":
        print_action("Creating new batch...")
        batch_id = start_new_batch(
            batch_type=pipeline_info['batch_type'],
            triggered_by='MANUAL_TEST',
            database_type='test'
        )
    elif choice == "2":
        batch_id_str = print_prompt("\nEnter existing batch ID: ").strip()
        try:
            batch_id = int(batch_id_str)
        except ValueError:
            print_error("Invalid batch ID. Will create new batch automatically.")
            batch_id = None
    else:  # choice == "3"
        print_action("Pipeline will create batch automatically...")
        batch_id = None
    
    return batch_id


def run_staging(pipeline_info, config):
    """Run the staging layer."""
    print_header("Running Staging Layer", Colors.BRIGHT_GREEN)
    
    # Configure batch
    batch_id = configure_batch(pipeline_info)
    
    # Create pipeline instance
    pipeline = pipeline_info['class'](
        batch_id=batch_id,
        snapshot_date=config['snapshot_date'],
        triggered_by='MANUAL_TEST',
        database_type='test'
    )
    
    # Run load_stage with configured parameters
    print_action("Loading stage...")
    try:
        if pipeline_info['name'] == 'Factory Inventory' or pipeline_info['name'] == 'Distributor Inventory':
            pipeline.load_stage(
                batch_size=config['batch_size'],
                incremental=config['incremental'],
                single_date_only=config['single_date_only']
            )
        elif pipeline_info['name'] == 'Sales Snapshot':
            pipeline.load_stage(
                batch_size=config['batch_size'],
                incremental=False,
                single_date_only=True
            )
        else:
            pipeline.load_stage()
        
        print_success("Load stage completed successfully!")
        return pipeline
    except Exception as e:
        print_error(f"Error: {str(e)}")
        raise


def run_publish(pipeline_info, config):
    """Run the publish layer."""
    print_header("Running Publish Layer", Colors.BRIGHT_GREEN)
    
    # Configure batch
    batch_id = configure_batch(pipeline_info)
    
    # Create pipeline instance
    pipeline = pipeline_info['class'](
        batch_id=batch_id,
        snapshot_date=config['snapshot_date'],
        triggered_by='MANUAL_TEST',
        database_type='test'
    )
    
    # Run publish
    print_action("Publishing...")
    try:
        pipeline.publish()
        print_success("Publish completed successfully!")
        return pipeline
    except Exception as e:
        print_error(f"Error: {str(e)}")
        raise


def run_full_pipeline(pipeline_info):
    """Run the full pipeline."""
    print_header("Running Full Pipeline", Colors.BRIGHT_GREEN)
    
    # Configure staging parameters (date control)
    staging_config = configure_staging(pipeline_info)
    
    # Configure batch
    batch_id = configure_batch(pipeline_info)
    
    # Create pipeline instance
    pipeline = pipeline_info['class'](
        batch_id=batch_id,
        snapshot_date=staging_config['snapshot_date'],
        triggered_by='MANUAL_TEST',
        database_type='test'
    )
    
    # Run full pipeline
    print_action("Running full pipeline (load_stage + publish)...")
    try:
        # Run load_stage with configured parameters
        print_action("Loading stage...")
        if pipeline_info['name'] == 'Factory Inventory' or pipeline_info['name'] == 'Distributor Inventory':
            pipeline.load_stage(
                batch_size=staging_config['batch_size'],
                incremental=staging_config['incremental'],
                single_date_only=staging_config['single_date_only']
            )
        elif pipeline_info['name'] == 'Sales Snapshot':
            pipeline.load_stage(
                batch_size=staging_config['batch_size'],
                incremental=False,
                single_date_only=True
            )
        else:
            pipeline.load_stage()
        
        # Run publish
        print_action("Publishing...")
        pipeline.publish()
        
        # Finish batch
        if hasattr(pipeline, 'batch_id') and pipeline.batch_id:
            pipeline.finish_batch(pipeline.batch_id, 'SUCCESS', 'OK')
        
        print_success("Full pipeline completed successfully!")
        return pipeline
    except Exception as e:
        # Handle batch failure
        if hasattr(pipeline, 'batch_id') and pipeline.batch_id:
            try:
                pipeline.finish_batch(pipeline.batch_id, 'FAILED', str(e))
            except Exception:
                pass
        print_error(f"Error: {str(e)}")
        raise


def handle_error(e):
    """Handle errors with helpful messages."""
    error_msg = str(e)
    print_error(f"Error: {error_msg}")
    
    # Check if it's a procedure not found error
    if "Could not find stored procedure" in error_msg or "2812" in error_msg:
        print_header("PROCEDURE NOT FOUND", Colors.BRIGHT_RED)
        print(colorize("The stored procedure has not been deployed to the database yet.", Colors.YELLOW))
        print()
        print_info("To fix this, run the deployment script:")
        print(colorize("  python scripts/deploy_procedures.py", Colors.BRIGHT_WHITE))
        print()
        print(colorize("This will deploy all stored procedures to the 'test' database.", Colors.DIM))
        print(colorize("If you need to deploy to a different database, use:", Colors.DIM))
        print(colorize("  python scripts/deploy_procedures.py <database_type>", Colors.BRIGHT_WHITE))
        print(colorize("  (where <database_type> is 'source' or 'test')", Colors.DIM))
    
    import traceback
    traceback.print_exc()


def main():
    """Main terminal interface for pipeline access."""
    print_header("ETL Pipeline Terminal Access", Colors.BRIGHT_CYAN)
    
    while True:
        # First layer: Select pipeline
        pipeline_info = select_pipeline()
        if pipeline_info is None:
            print()
            print_info("Goodbye!")
            break
        
        # Second layer: Select layer/operation
        while True:
            layer_choice = select_layer(pipeline_info)
            
            if layer_choice == 'b':
                break
            elif layer_choice == 'q':
                print()
                print_info("Goodbye!")
                sys.exit(0)
            elif layer_choice == '1':
                # Staging layer
                try:
                    config = configure_staging(pipeline_info)
                    run_staging(pipeline_info, config)
                except Exception as e:
                    handle_error(e)
            elif layer_choice == '2':
                # Publish layer
                try:
                    config = configure_publish(pipeline_info)
                    run_publish(pipeline_info, config)
                except Exception as e:
                    handle_error(e)
            elif layer_choice == '3':
                # Full pipeline
                try:
                    run_full_pipeline(pipeline_info)
                except Exception as e:
                    handle_error(e)
            else:
                print_error("Invalid choice. Please try again.")
            
            # Ask if user wants to continue with this pipeline
            continue_choice = print_prompt("\nContinue with this pipeline? (y/n, default=y): ").strip().lower()
            if continue_choice == 'n':
                break


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print()
        print()
        print_warning("Interrupted by user. Goodbye!")
        sys.exit(0)
