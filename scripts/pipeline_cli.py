"""Terminal access tool for ETL pipelines."""

import sys
import os
import time
from datetime import date, datetime
from pathlib import Path
from typing import Optional

# Set UTF-8 encoding for Windows terminal to display Farsi characters
if sys.platform == 'win32':
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

    os.environ['PYTHONIOENCODING'] = 'utf-8'
    os.environ['PYTHONLEGACYWINDOWSSTDIO'] = '0'

    try:
        import subprocess
        subprocess.run(['chcp', '65001'], shell=True, capture_output=True, check=False)
    except Exception:
        pass

    try:
        import locale
        locale.setlocale(locale.LC_ALL, 'en_US.UTF-8')
    except Exception:
        try:
            locale.setlocale(locale.LC_ALL, '')
        except Exception:
            pass

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.orchestrator.pipelines.factory_inventory import FactoryInventoryPipeline
from src.orchestrator.pipelines.distributor_inventory import DistributorInventoryPipeline
from src.orchestrator.pipelines.sales_snapshot import SalesSnapshotPipeline
from src.orchestrator.pipelines.target import TargetPipeline
from src.orchestrator.pipelines.distributor_deliveries import DistributorDeliveriesPipeline
from src.orchestrator.services.sql_server_db.factory import DBConnectionFactory
from src.orchestrator.services.sql_server_db.executors.sql_executor import SQLExecutor
from src.orchestrator.services.vpn import ensure_vpn_connected
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

SQL_SOURCE_PIPELINES = frozenset({
    'Factory Inventory',
    'Distributor Inventory',
    'Sales Snapshot',
    'Target',
})


def is_sql_source_pipeline(pipeline_info) -> bool:
    return pipeline_info['name'] in SQL_SOURCE_PIPELINES


def prompt_force_historical_reload() -> bool:
    choice = print_prompt(
        "Force full reload (erase ALL fact rows incl. historical year)? "
        "Normal runs keep historical year (y/N): "
    ).strip().lower()
    return choice == 'y'


def format_duration(seconds: float) -> str:
    if seconds < 60:
        return f"{seconds:.1f}s"
    minutes, secs = divmod(int(seconds), 60)
    if minutes < 60:
        return f"{minutes}m {secs}s"
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h {minutes}m {secs}s"


def make_pipeline_log_fn(pipeline_name: str):
    """Build a timestamped log callback for pipeline progress messages."""

    def log_fn(message: str) -> None:
        stamp = datetime.now().strftime("%H:%M:%S")
        print_info(f"[{pipeline_name}] [{stamp}] {message}")

    return log_fn


def print_kv(label: str, value: str, indent: int = 2) -> None:
    prefix = " " * indent
    print(colorize(f"{prefix}{label}: ", Colors.DIM) + colorize(str(value), Colors.WHITE))


def prompt_snapshot_date() -> Optional[date]:
    """Ask for snapshot date; Enter means today (None → pipeline default)."""
    print_info("Snapshot date (filters source data and stamps published rows):")
    print(colorize("  Enter = today", Colors.DIM))
    raw = print_prompt("  YYYY-MM-DD or Enter: ").strip()
    if not raw:
        return None
    try:
        year, month, day = map(int, raw.split('-'))
        return date(year, month, day)
    except ValueError:
        print_warning("Invalid date — using today.")
        return None


def print_run_plan(
    pipeline_info,
    *,
    operation: str,
    batch_id: Optional[int] = None,
    snapshot_date: Optional[date] = None,
    config: Optional[dict] = None,
) -> None:
    """Single pre-run summary."""
    print_header("Ready to run", Colors.BRIGHT_BLUE)
    print_kv("Pipeline", pipeline_info['name'])
    print_kv("Operation", operation)
    if batch_id is not None:
        print_kv("Batch ID", batch_id)
    snap = snapshot_date or (config or {}).get('snapshot_date') or date.today()
    print_kv("Snapshot date", snap.isoformat() if hasattr(snap, 'isoformat') else snap)

    if pipeline_info['name'] in ('Factory Inventory', 'Distributor Inventory'):
        print_kv("Data window", f"Source FKDate = {snap}")
    elif pipeline_info['name'] == 'Sales Snapshot':
        print_kv("Data window", "Rolling ~7 Jalali months ending on snapshot date")
    elif pipeline_info['name'] == 'Target':
        print_kv("Data window", "Jalali year + month of snapshot date")
    elif pipeline_info['name'] == 'Distributor Deliveries' and config is not None:
        print_kv(
            "Reload historical year",
            "yes" if config.get('force_historical_reload') else "no (keep historical)",
        )
        if config.get('batch_size'):
            print_kv("Insert batch size", f"{config['batch_size']:,}")
    print()


def print_run_footer(pipeline, operation: str, elapsed: float, success: bool) -> None:
    outcome = colorize("OK", Colors.BRIGHT_GREEN) if success else colorize("FAILED", Colors.BRIGHT_RED)
    batch_id = getattr(pipeline, 'batch_id', '—')
    print()
    print(
        colorize(f"  {outcome}", Colors.WHITE)
        + colorize(f"  |  batch {batch_id}  |  {format_duration(elapsed)}  |  {operation}", Colors.DIM)
    )
    print()


def build_pipeline_kwargs(pipeline_info, batch_id, snapshot_date, log: bool = True) -> dict:
    kwargs = {
        'batch_id': batch_id,
        'snapshot_date': snapshot_date,
        'triggered_by': 'MANUAL_TEST',
        'database_type': 'prod',
    }
    if pipeline_info['name'] == 'Distributor Deliveries':
        kwargs['log_fn'] = print_info if log else None
        kwargs['show_progress'] = log
    elif log:
        kwargs['log_fn'] = make_pipeline_log_fn(pipeline_info['name'])
    return kwargs


def start_new_batch(batch_type: str, triggered_by: str = 'MANUAL_TEST', database_type: str = 'prod', pipeline_name: str = None) -> int:
    """Start a new batch and return the batch_id."""
    connection_factory = DBConnectionFactory()
    sql_executor = SQLExecutor(connection_factory)

    result = sql_executor.execute_procedure_with_output(
        procedure_name=connection_factory.qualify('ctl_usp_start_batch', database_type),
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
    print()
    print_menu_item('a', 'Full Automate Pipeline (Run All)', Colors.BRIGHT_GREEN)
    print_menu_item('q', 'Quit', Colors.BRIGHT_YELLOW)

    choice = print_prompt("\nSelect pipeline: ").strip().lower()
    if choice == 'q':
        return None
    if choice == 'a':
        return 'ALL'
    return PIPELINES.get(choice)


def select_operation(pipeline_info):
    """Choose what to run for the selected pipeline."""
    print_header(f"{pipeline_info['name']}", Colors.BRIGHT_CYAN)
    if is_sql_source_pipeline(pipeline_info):
        print(colorize("  Snapshot (reads DWOrchid directly via stored proc)", Colors.DIM))
        print_menu_item('1', 'Publish snapshot only', Colors.BRIGHT_WHITE)
        print_menu_item('2', 'Full pipeline (prepare batch + publish)', Colors.BRIGHT_WHITE)
    elif pipeline_info['name'] == 'Distributor Deliveries':
        print_menu_item('1', 'Load fact table from DMS', Colors.BRIGHT_WHITE)
        print_menu_item('2', 'Publish snapshot', Colors.BRIGHT_WHITE)
        print_menu_item('3', 'Full pipeline (load fact + publish)', Colors.BRIGHT_WHITE)
    print()
    print_menu_item('b', 'Back', Colors.BRIGHT_YELLOW)
    print_menu_item('q', 'Quit', Colors.BRIGHT_YELLOW)

    return print_prompt("\nChoice: ").strip().lower()


def configure_sql_options(pipeline_info):
    """Options for DWOrchid SQL snapshot pipelines."""
    print_header("Options", Colors.BRIGHT_BLUE)
    return {'snapshot_date': prompt_snapshot_date()}


def configure_deliveries_load():
    """Options for DMS → fact load."""
    print_header("Options", Colors.BRIGHT_BLUE)
    snapshot_date = prompt_snapshot_date()
    batch_size = 10000
    batch_size_str = print_prompt("Insert batch size (default 10000): ").strip()
    if batch_size_str:
        try:
            batch_size = int(batch_size_str)
        except ValueError:
            print_warning("Invalid — using 10000.")
    return {
        'snapshot_date': snapshot_date,
        'batch_size': batch_size,
        'force_historical_reload': prompt_force_historical_reload(),
    }


def configure_publish(pipeline_info):
    print_header("Publish options", Colors.BRIGHT_BLUE)
    return {'snapshot_date': prompt_snapshot_date()}


def configure_batch(pipeline_info) -> Optional[int]:
    """Pick or create the batch ID for this run."""
    print_header("Batch", Colors.BRIGHT_BLUE)
    print_menu_item('1', 'Create new batch (recommended)', Colors.BRIGHT_WHITE)
    print_menu_item('2', 'Reuse existing batch ID', Colors.WHITE)
    choice = print_prompt("  1 or 2 (default 1): ").strip() or "1"

    if choice == "2":
        batch_id_str = print_prompt("Batch ID: ").strip()
        try:
            return int(batch_id_str)
        except ValueError:
            print_error("Invalid batch ID.")
            raise ValueError("invalid batch_id")

    print_action("Creating batch...")
    return start_new_batch(
        batch_type=pipeline_info['batch_type'],
        triggered_by='MANUAL_TEST',
        database_type='prod',
        pipeline_name=pipeline_info['name'],
    )


def run_deliveries_load(pipeline_info, config):
    """Load DMS Excel files into the fact table."""
    batch_id = configure_batch(pipeline_info)
    print_run_plan(
        pipeline_info,
        operation="Load fact table from DMS",
        batch_id=batch_id,
        config=config,
    )

    pipeline = pipeline_info['class'](
        **build_pipeline_kwargs(pipeline_info, batch_id, config['snapshot_date'])
    )

    started = time.monotonic()
    print_action("Running...")
    try:
        pipeline.load_stage(
            batch_size=config['batch_size'],
            force_historical_reload=config.get('force_historical_reload', False),
        )
        elapsed = time.monotonic() - started
        print_run_footer(pipeline, "Load fact", elapsed, success=True)
        return pipeline
    except Exception:
        elapsed = time.monotonic() - started
        print_run_footer(pipeline, "Load fact", elapsed, success=False)
        raise


def run_publish(pipeline_info, config):
    """Run the publish layer."""
    batch_id = configure_batch(pipeline_info)
    print_run_plan(
        pipeline_info,
        operation="Publish snapshot",
        batch_id=batch_id,
        snapshot_date=config.get('snapshot_date'),
    )

    pipeline = pipeline_info['class'](
        **build_pipeline_kwargs(pipeline_info, batch_id, config['snapshot_date'], log=False)
    )

    started = time.monotonic()
    print_action("Publishing...")
    try:
        pipeline.publish()
        elapsed = time.monotonic() - started
        print_run_footer(pipeline, "Publish", elapsed, success=True)
        return pipeline
    except Exception:
        elapsed = time.monotonic() - started
        print_run_footer(pipeline, "Publish", elapsed, success=False)
        raise


def run_full_pipeline(pipeline_info):
    """Run the full pipeline (prepare/load, then publish)."""
    if is_sql_source_pipeline(pipeline_info):
        config = configure_sql_options(pipeline_info)
        operation = "Full pipeline (prepare batch + publish)"
    else:
        config = configure_deliveries_load()
        operation = "Full pipeline (load fact + publish)"

    batch_id = configure_batch(pipeline_info)
    print_run_plan(
        pipeline_info,
        operation=operation,
        batch_id=batch_id,
        config=config,
    )

    pipeline = pipeline_info['class'](
        **build_pipeline_kwargs(pipeline_info, batch_id, config['snapshot_date'])
    )

    started = time.monotonic()
    try:
        if pipeline_info['name'] == 'Distributor Deliveries':
            # Keep _in_run_method True so load_stage does not finish SUCCESS mid-run.
            pipeline._in_run_method = True
            try:
                pipeline.load_stage(
                    batch_size=config.get('batch_size', 10000),
                    force_historical_reload=config.get('force_historical_reload', False),
                )
                pipeline.publish()
                if pipeline.batch_id:
                    pipeline.finish_batch(pipeline.batch_id, 'SUCCESS', 'OK')
            except Exception as e:
                if pipeline.batch_id:
                    try:
                        pipeline.finish_batch(pipeline.batch_id, 'FAILED', str(e))
                    except Exception:
                        pass
                raise
            finally:
                pipeline._in_run_method = False
        else:
            pipeline.run()
        elapsed = time.monotonic() - started
        print_run_footer(pipeline, "Full pipeline", elapsed, success=True)
        return pipeline
    except Exception:
        elapsed = time.monotonic() - started
        print_run_footer(pipeline, "Full pipeline", elapsed, success=False)
        raise


def run_full_automate_pipeline():
    """Run all pipelines with today's date and auto-created batches on prod."""
    print_header("Full Automate Pipeline - Running All Pipelines", Colors.BRIGHT_MAGENTA)
    print_info("All pipelines run with today's snapshot date and auto-created batches on prod.")
    print()

    total = len(PIPELINES)
    succeeded = []
    failed = []

    for key, pipeline_info in PIPELINES.items():
        pipeline_name = pipeline_info['name']
        print_header(f"[{key}/{total}] {pipeline_name}", Colors.BRIGHT_CYAN)
        try:
            print_action(f"[{pipeline_name}] Creating batch...")
            batch_id = start_new_batch(
                batch_type=pipeline_info['batch_type'],
                triggered_by='MANUAL_TEST',
                database_type='prod',
                pipeline_name=pipeline_name
            )

            pipeline = pipeline_info['class'](
                **build_pipeline_kwargs(pipeline_info, batch_id, None)
            )
            step_started = time.monotonic()

            print_action(f"[{pipeline_name}] Running pipeline...")
            pipeline.run()

            elapsed = time.monotonic() - step_started
            print_success(
                f"[{pipeline_name}] Completed successfully in {format_duration(elapsed)}!"
            )
            succeeded.append(pipeline_name)

        except Exception as e:
            print_error(f"[{pipeline_name}] Failed: {e}")
            import traceback
            traceback.print_exc()
            failed.append(pipeline_name)

        print()

    print_header("Full Automate Pipeline - Summary", Colors.BRIGHT_MAGENTA)
    print_info(f"Total pipelines: {total}")
    if succeeded:
        print_success(f"Succeeded ({len(succeeded)}): {', '.join(succeeded)}")
    if failed:
        print_error(f"Failed    ({len(failed)}): {', '.join(failed)}")
    if not failed:
        print_success("All pipelines completed successfully!")


def handle_error(e):
    """Handle errors with helpful messages."""
    error_msg = str(e)
    print_error(error_msg)

    if "Could not find stored procedure" in error_msg or "2812" in error_msg:
        print_header("PROCEDURE NOT FOUND", Colors.BRIGHT_RED)
        print(colorize("The stored procedure has not been deployed to the database yet.", Colors.YELLOW))
        print()
        print_info("To fix this, run the deployment script:")
        print(colorize("  python scripts/deploy_procedures.py", Colors.BRIGHT_WHITE))
        print()
        print(colorize("This will deploy all stored procedures to the 'prod' database.", Colors.DIM))
        print(colorize("If you need to deploy to a different database, use:", Colors.DIM))
        print(colorize("  python scripts/deploy_procedures.py <database_type>", Colors.BRIGHT_WHITE))
        print(colorize("  (where <database_type> is 'source' or 'prod')", Colors.DIM))


def main():
    """Main terminal interface for pipeline access."""
    print_header("ETL Pipeline Terminal Access", Colors.BRIGHT_CYAN)

    ensure_vpn_connected(log_fn=print_info, prompt_fn=print_prompt)

    while True:
        pipeline_info = select_pipeline()
        if pipeline_info is None:
            print()
            print_info("Goodbye!")
            break

        if pipeline_info == 'ALL':
            try:
                run_full_automate_pipeline()
            except Exception as e:
                handle_error(e)
            continue

        while True:
            choice = select_operation(pipeline_info)

            if choice == 'b':
                break
            elif choice == 'q':
                print()
                print_info("Goodbye!")
                sys.exit(0)

            sql = is_sql_source_pipeline(pipeline_info)

            try:
                if sql and choice == '1':
                    config = configure_publish(pipeline_info)
                    run_publish(pipeline_info, config)
                elif sql and choice == '2':
                    run_full_pipeline(pipeline_info)
                elif pipeline_info['name'] == 'Distributor Deliveries' and choice == '1':
                    config = configure_deliveries_load()
                    run_deliveries_load(pipeline_info, config)
                elif pipeline_info['name'] == 'Distributor Deliveries' and choice == '2':
                    config = configure_publish(pipeline_info)
                    run_publish(pipeline_info, config)
                elif pipeline_info['name'] == 'Distributor Deliveries' and choice == '3':
                    run_full_pipeline(pipeline_info)
                else:
                    print_error("Invalid choice.")
                    continue
            except Exception as e:
                handle_error(e)
                import traceback
                traceback.print_exc()

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
