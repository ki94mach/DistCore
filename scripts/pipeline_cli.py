"""Terminal access tool for ETL pipelines."""

import sys
import os
from pathlib import Path
from datetime import date

# Set UTF-8 encoding for Windows terminal to display Farsi characters
if sys.platform == 'win32':
    # Method 1: Try to reconfigure stdout/stderr
    if hasattr(sys.stdout, 'reconfigure'):
        try:
            sys.stdout.reconfigure(encoding='utf-8')
        except Exception:
            pass
    if hasattr(sys.stderr, 'reconfigure'):
        try:
            sys.stderr.reconfigure(encoding='utf-8')
        except Exception:
            pass
    
    # Method 2: Set environment variables
    os.environ['PYTHONIOENCODING'] = 'utf-8'
    os.environ['PYTHONLEGACYWINDOWSSTDIO'] = '0'
    
    # Method 3: Try to change console code page to UTF-8 (65001)
    try:
        import subprocess
        # Change console code page to UTF-8
        subprocess.run(['chcp', '65001'], shell=True, capture_output=True, check=False)
    except Exception:
        pass
    
    # Method 4: Set locale if available
    try:
        import locale
        locale.setlocale(locale.LC_ALL, 'en_US.UTF-8')
    except Exception:
        try:
            locale.setlocale(locale.LC_ALL, '')
        except Exception:
            pass

# Add project root to Python path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.orchestrator.pipelines.factory_inventory import FactoryInventoryPipeline
from src.orchestrator.pipelines.distributor_inventory import DistributorInventoryPipeline
from src.orchestrator.pipelines.sales_snapshot import SalesSnapshotPipeline
from src.orchestrator.pipelines.target import TargetPipeline
from src.orchestrator.pipelines.distributor_deliveries import DistributorDeliveriesPipeline
from src.orchestrator.services.sql_server_db.factory import DBConnectionFactory
from src.orchestrator.services.sql_server_db.executors.sql_executor import SQLExecutor
from src.orchestrator.ui.terminal_ui import (
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
    },
    '4': {
        'name': 'Target',
        'class': TargetPipeline,
        'batch_type': 'TARGET'
    },
    '5': {
        'name': 'Distributor Deliveries',
        'class': DistributorDeliveriesPipeline,
        'batch_type': 'DISTRIBUTOR_DELIVERIES'
    }
}


def start_new_batch(batch_type: str, triggered_by: str = 'MANUAL_TEST', database_type: str = 'test', pipeline_name: str = None) -> int:
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
    if pipeline_name:
        print_success(f"[{pipeline_name}] Created new batch ID: {batch_id}")
    else:
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
            "  - Sales snapshots load a rolling six-month window ending on the snapshot date.",
            Colors.DIM
        ))
        incremental = False
        single_date_only = False
    elif pipeline_info['name'] == 'Target':
        print_info("\nLoad Mode:")
        print(colorize(
            "  - Target pipeline loads data for the current Jalali year only.",
            Colors.DIM
        ))
        incremental = False
        single_date_only = False
    
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
            database_type='test',
            pipeline_name=pipeline_info['name']
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


def check_loaded_delivery_files(
    connection_factory: DBConnectionFactory,
    snapshot_date: date,
    database_type: str
) -> None:
    """
    Check and display which delivery files were successfully loaded for the snapshot date.
    
    Args:
        connection_factory: Database connection factory
        snapshot_date: Snapshot date to check
        database_type: Database type ('source' or 'test')
    """
    try:
        import pyodbc
        from src.orchestrator.services.sql_server_db.executors.result_formatter import format_result_set
        
        # First, try to find batch_id from snapshot table for this date
        # If snapshot exists, use its batch_id; otherwise, find latest batch before snapshot date
        query = """
        SELECT DISTINCT
            stg.source_file,
            COUNT(*) as row_count,
            MAX(stg.ingested_at) as last_loaded
        FROM [Data].[stg_DistributorDeliveries] stg
        WHERE stg.batch_id IN (
            -- Get batch_id from snapshot if it exists for this date
            SELECT DISTINCT batch_id 
            FROM [Data].[snp_DistributorDeliveriesSnapshot]
            WHERE snapshot_date = ?
            UNION
            -- Otherwise, get the latest batch_id before or on this date
            SELECT TOP 1 batch_id
            FROM [Data].[Batch]
            WHERE batch_type = 'DISTRIBUTOR_DELIVERIES'
              AND snapshot_date <= ?
            ORDER BY snapshot_date DESC, batch_id DESC
        )
        GROUP BY stg.source_file
        ORDER BY stg.source_file
        """
        
        with connection_factory.connection(database_type) as conn:
            cursor = conn.cursor()
            cursor.execute(query, (snapshot_date, snapshot_date))
            results = format_result_set(cursor)
            conn.commit()
        
        if results:
            print_info(f"\n✓ Delivery files successfully loaded for snapshot date {snapshot_date}:")
            total_rows = 0
            for row in results:
                source_file = row.get('source_file', 'Unknown')
                row_count = row.get('row_count', 0)
                total_rows += row_count
                if source_file:
                    print_info(f"  - {colorize(source_file, Colors.BRIGHT_WHITE)} ({row_count} rows)")
            print_info(f"Total: {len(results)} file(s), {total_rows} row(s)")
        else:
            print_warning(f"No delivery files found for snapshot date {snapshot_date}")
            print_info("  Note: This may indicate that the distributor deliveries pipeline has not been run for this date.")
    except Exception as e:
        # Don't fail the pipeline if file checking fails
        print_warning(f"Could not check loaded delivery files: {e}")


def run_staging(pipeline_info, config):
    """Run the staging layer."""
    print_header("Running Staging Layer", Colors.BRIGHT_GREEN)
    
    # Configure batch
    batch_id = configure_batch(pipeline_info)
    
    # Create pipeline instance
    pipeline_kwargs = {
        'batch_id': batch_id,
        'snapshot_date': config['snapshot_date'],
        'triggered_by': 'MANUAL_TEST',
        'database_type': 'test'
    }
    
    pipeline = pipeline_info['class'](**pipeline_kwargs)
    
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
                batch_size=config['batch_size']
            )
        elif pipeline_info['name'] == 'Target':
            pipeline.load_stage(
                batch_size=config['batch_size'],
                incremental=config['incremental'],
                single_date_only=config['single_date_only']
            )
        else:
            pipeline.load_stage()
        
        print_success(f"[{pipeline_info['name']}] Load stage completed successfully!")
        
        # Check loaded files for Distributor Deliveries pipeline
        if pipeline_info['name'] == 'Distributor Deliveries' and config.get('snapshot_date'):
            print_action("Checking loaded delivery files...")
            connection_factory = DBConnectionFactory()
            check_loaded_delivery_files(
                connection_factory=connection_factory,
                snapshot_date=config['snapshot_date'],
                database_type='test'
            )
        
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
    pipeline_kwargs = {
        'batch_id': batch_id,
        'snapshot_date': config['snapshot_date'],
        'triggered_by': 'MANUAL_TEST',
        'database_type': 'test'
    }
    
    pipeline = pipeline_info['class'](**pipeline_kwargs)
    
    # Run publish
    print_action("Publishing...")
    try:
        pipeline.publish()
        print_success(f"[{pipeline_info['name']}] Publish completed successfully!")
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
    pipeline_kwargs = {
        'batch_id': batch_id,
        'snapshot_date': staging_config['snapshot_date'],
        'triggered_by': 'MANUAL_TEST',
        'database_type': 'test'
    }
    
    pipeline = pipeline_info['class'](**pipeline_kwargs)
    
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
                batch_size=staging_config['batch_size']
            )
        elif pipeline_info['name'] == 'Target':
            pipeline.load_stage(
                batch_size=staging_config['batch_size'],
                incremental=staging_config['incremental'],
                single_date_only=staging_config['single_date_only']
            )
        elif pipeline_info['name'] == 'Distributor Deliveries':
            pipeline.load_stage(
                batch_size=staging_config['batch_size']
            )
        else:
            pipeline.load_stage()
        
        # Check loaded files for Distributor Deliveries pipeline after staging
        if pipeline_info['name'] == 'Distributor Deliveries' and staging_config.get('snapshot_date'):
            print_action("Checking loaded delivery files...")
            connection_factory = DBConnectionFactory()
            check_loaded_delivery_files(
                connection_factory=connection_factory,
                snapshot_date=staging_config['snapshot_date'],
                database_type='test'
            )
        
        # Run publish
        print_action("Publishing...")
        pipeline.publish()
        
        # Finish batch
        if hasattr(pipeline, 'batch_id') and pipeline.batch_id:
            pipeline.finish_batch(pipeline.batch_id, 'SUCCESS', 'OK')
        
        print_success(f"[{pipeline_info['name']}] Full pipeline completed successfully!")
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
