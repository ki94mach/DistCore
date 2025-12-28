import time
from typing import Dict, Optional, Tuple
from .db import DBConnectionFactory


class DatabaseHealthChecker:
    """
    Health checker for database connections.
    Provides methods to verify database connectivity and performance.
    """
    
    def __init__(self, factory: Optional[DBConnectionFactory] = None):
        """
        Initialize the health checker.
        
        Args:
            factory: Optional DBConnectionFactory instance. If None, creates a new one.
        """
        self.factory = factory or DBConnectionFactory()
    
    def check_health(self, database_type: str = 'source', timeout: float = 5.0) -> Dict[str, any]:
        """
        Perform a health check on the specified database.
        
        Args:
            database_type: Type of database to check ('source' or 'test')
            timeout: Maximum time in seconds to wait for connection
        
        Returns:
            Dictionary containing:
                - status: 'healthy' or 'unhealthy'
                - database_type: The database type checked
                - response_time_ms: Connection response time in milliseconds
                - error: Error message if unhealthy, None otherwise
                - timestamp: When the check was performed
        """
        start_time = time.time()
        result = {
            'status': 'unhealthy',
            'database_type': database_type,
            'response_time_ms': None,
            'error': None,
            'timestamp': time.time()
        }
        
        try:
            # Attempt to get a connection
            connection = self.factory.get_connection(database_type)
            
            # Perform a simple query to verify the connection works
            cursor = connection.cursor()
            cursor.execute("SELECT 1")
            cursor.fetchone()
            cursor.close()
            connection.close()
            
            # Calculate response time
            elapsed_time = time.time() - start_time
            result['response_time_ms'] = round(elapsed_time * 1000, 2)
            
            # Check if within timeout
            if elapsed_time <= timeout:
                result['status'] = 'healthy'
            else:
                result['error'] = f"Health check exceeded timeout of {timeout}s"
            
        except Exception as e:
            elapsed_time = time.time() - start_time
            result['response_time_ms'] = round(elapsed_time * 1000, 2)
            result['error'] = str(e)
        
        return result
    
    def check_all_databases(self, timeout: float = 5.0) -> Dict[str, Dict[str, any]]:
        """
        Check health of all configured databases.
        
        Args:
            timeout: Maximum time in seconds to wait for each connection
        
        Returns:
            Dictionary mapping database types to their health check results
        """
        config = self.factory.get_config()
        if not config or 'databases' not in config:
            return {}
        
        results = {}
        # Get all database types (excluding driver, username, password)
        db_types = [
            key for key in config['databases'].keys() 
            if key not in ['driver', 'username', 'password']
        ]
        
        for db_type in db_types:
            results[db_type] = self.check_health(db_type, timeout)
        
        return results
    
    def is_healthy(self, database_type: str = 'source', timeout: float = 5.0) -> bool:
        """
        Simple boolean check for database health.
        
        Args:
            database_type: Type of database to check
            timeout: Maximum time in seconds to wait for connection
        
        Returns:
            True if healthy, False otherwise
        """
        result = self.check_health(database_type, timeout)
        return result['status'] == 'healthy'
    
    def get_health_summary(self, timeout: float = 5.0) -> Dict[str, any]:
        """
        Get a summary of all database health checks.
        
        Args:
            timeout: Maximum time in seconds to wait for each connection
        
        Returns:
            Dictionary containing:
                - overall_status: 'healthy' if all databases are healthy, 'degraded' if some are unhealthy, 'unhealthy' if all are unhealthy
                - databases: Dictionary of individual database health checks
                - healthy_count: Number of healthy databases
                - total_count: Total number of databases checked
        """
        all_checks = self.check_all_databases(timeout)
        
        healthy_count = sum(1 for check in all_checks.values() if check['status'] == 'healthy')
        total_count = len(all_checks)
        
        if healthy_count == total_count and total_count > 0:
            overall_status = 'healthy'
        elif healthy_count > 0:
            overall_status = 'degraded'
        else:
            overall_status = 'unhealthy'
        
        return {
            'overall_status': overall_status,
            'databases': all_checks,
            'healthy_count': healthy_count,
            'total_count': total_count,
            'timestamp': time.time()
        }

