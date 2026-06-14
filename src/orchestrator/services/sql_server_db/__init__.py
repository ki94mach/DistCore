"""
Database connection factory module.

This module provides a singleton factory for creating and managing database connections
with connection pooling, health checking, and automatic resource management.

Usage Examples:
    
    # Default: Uses default config path (backward compatible)
    from db import DBConnectionFactory
    factory = DBConnectionFactory()
    
    # From config file path
    from pathlib import Path
    factory = DBConnectionFactory.from_config_file(Path('/path/to/config.yml'))
    
    # From config dictionary (no file needed)
    config = {
        'databases': {
            'driver': 'ODBC Driver 17 for SQL Server',
            'use_windows_auth': True,
            'source': {
                'server': 'myserver',
                'database': 'mydb'
            }
        }
    }
    factory = DBConnectionFactory.from_config_dict(config)
    
    # Use the factory
    with factory.connection('source') as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM table")
"""

from .factory import DBConnectionFactory
from .context import ConnectionContextManager
from .executors.sql_executor import SQLExecutor
from .schema import DEFAULT_SCHEMA, qualify_object, qualify_cross_db

__all__ = [
    'DBConnectionFactory',
    'ConnectionContextManager',
    'SQLExecutor',
    'DEFAULT_SCHEMA',
    'qualify_object',
    'qualify_cross_db',
]

