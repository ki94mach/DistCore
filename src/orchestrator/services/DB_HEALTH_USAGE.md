# DatabaseHealthChecker Usage Guide

The `DatabaseHealthChecker` provides high-level health monitoring for your database connections with timeouts, response time metrics, and comprehensive summaries.

## Quick Start

```python
from db_health import DatabaseHealthChecker

# Create a health checker
health_checker = DatabaseHealthChecker()

# Check if database is healthy
is_healthy = health_checker.is_healthy('source')
print(f"Database is healthy: {is_healthy}")
```

## Methods Overview

### 1. `check_health(database_type, timeout)` - Detailed Health Check

Returns a detailed dictionary with health status, response time, and error information.

```python
from db_health import DatabaseHealthChecker

health_checker = DatabaseHealthChecker()

# Check source database with 5 second timeout
result = health_checker.check_health('source', timeout=5.0)

print(result)
# Output:
# {
#     'status': 'healthy',           # or 'unhealthy'
#     'database_type': 'source',
#     'response_time_ms': 45.23,     # Response time in milliseconds
#     'error': None,                  # Error message if unhealthy
#     'timestamp': 1703847123.456     # Unix timestamp
# }
```

**Use Cases:**

- Detailed health monitoring
- Logging health metrics
- API health endpoints
- Alerting systems

### 2. `is_healthy(database_type, timeout)` - Simple Boolean Check

Returns `True` if healthy, `False` otherwise.

```python
health_checker = DatabaseHealthChecker()

if health_checker.is_healthy('source', timeout=5.0):
    print("✅ Database is healthy!")
    # Proceed with operations
else:
    print("❌ Database is unhealthy!")
    # Handle error or retry
```

**Use Cases:**

- Quick health checks before operations
- Conditional logic based on health
- Simple monitoring scripts

### 3. `check_all_databases(timeout)` - Check All Databases

Checks health of all configured databases and returns a dictionary mapping database types to their results.

```python
health_checker = DatabaseHealthChecker()

# Check all databases
all_results = health_checker.check_all_databases(timeout=5.0)

# all_results structure:
# {
#     'source': {
#         'status': 'healthy',
#         'response_time_ms': 45.23,
#         ...
#     },
#     'test': {
#         'status': 'healthy',
#         'response_time_ms': 38.12,
#         ...
#     }
# }

for db_type, result in all_results.items():
    print(f"{db_type}: {result['status']} ({result['response_time_ms']} ms)")
```

**Use Cases:**

- Monitoring dashboards
- Health reports
- Batch health checks

### 4. `get_health_summary(timeout)` - Comprehensive Summary

Returns an overall health summary with aggregated statistics.

```python
health_checker = DatabaseHealthChecker()

summary = health_checker.get_health_summary(timeout=5.0)

print(summary)
# Output:
# {
#     'overall_status': 'healthy',      # 'healthy', 'degraded', or 'unhealthy'
#     'databases': { ... },             # Individual database results
#     'healthy_count': 2,               # Number of healthy databases
#     'total_count': 2,                 # Total number of databases
#     'timestamp': 1703847123.456        # When check was performed
# }

# Check overall status
if summary['overall_status'] == 'healthy':
    print("All databases are healthy!")
elif summary['overall_status'] == 'degraded':
    print(f"Some databases are unhealthy: {summary['healthy_count']}/{summary['total_count']} healthy")
else:
    print("All databases are unhealthy!")
```

**Status Values:**

- `'healthy'`: All databases are healthy
- `'degraded'`: Some databases are unhealthy
- `'unhealthy'`: All databases are unhealthy

**Use Cases:**

- Health dashboards
- Monitoring alerts
- System status reports
- API health endpoints

## Complete Examples

### Example 1: Basic Health Check

```python
from db_health import DatabaseHealthChecker

health_checker = DatabaseHealthChecker()
result = health_checker.check_health('source')

if result['status'] == 'healthy':
    print(f"✅ Database is healthy! Response time: {result['response_time_ms']} ms")
else:
    print(f"❌ Database is unhealthy: {result['error']}")
```

### Example 2: Monitoring Script

```python
import time
from db_health import DatabaseHealthChecker

health_checker = DatabaseHealthChecker()

print("Starting database monitoring...")
while True:
    summary = health_checker.get_health_summary(timeout=5.0)

    timestamp = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(summary['timestamp']))
    print(f"[{timestamp}] Status: {summary['overall_status']} | "
          f"Healthy: {summary['healthy_count']}/{summary['total_count']}")

    # Alert if unhealthy
    if summary['overall_status'] != 'healthy':
        print("⚠️  ALERT: Database health issue detected!")

    time.sleep(60)  # Check every minute
```

### Example 3: API Health Endpoint

```python
from flask import Flask, jsonify
from db_health import DatabaseHealthChecker

app = Flask(__name__)
health_checker = DatabaseHealthChecker()

@app.route('/health')
def health_endpoint():
    """Health check endpoint for load balancers."""
    summary = health_checker.get_health_summary(timeout=2.0)

    status_code = 200 if summary['overall_status'] == 'healthy' else 503
    return jsonify(summary), status_code

@app.route('/health/<database_type>')
def database_health(database_type):
    """Health check for specific database."""
    result = health_checker.check_health(database_type, timeout=2.0)

    status_code = 200 if result['status'] == 'healthy' else 503
    return jsonify(result), status_code
```

### Example 4: Pre-flight Check Before Operations

```python
from db_health import DatabaseHealthChecker

health_checker = DatabaseHealthChecker()

def perform_critical_operation():
    # Check health before critical operation
    if not health_checker.is_healthy('source', timeout=3.0):
        raise Exception("Cannot perform operation: database is unhealthy")

    # Proceed with operation
    with factory.connection('source') as conn:
        # ... your operations ...
        pass
```

### Example 5: Custom Factory

```python
from db_health import DatabaseHealthChecker
from sql_server_db import DBConnectionFactory
from pathlib import Path

# Create factory with custom config
factory = DBConnectionFactory.from_config_file(Path('/custom/path/config.yml'))

# Use with health checker
health_checker = DatabaseHealthChecker(factory=factory)

result = health_checker.check_health('source')
```

## Best Practices

1. **Set Appropriate Timeouts**: Use shorter timeouts (2-3 seconds) for quick checks, longer (5-10 seconds) for detailed monitoring.

2. **Handle Errors Gracefully**: Always wrap health checks in try-except blocks for production code.

3. **Use Context Managers**: The health checker automatically uses connection pooling, so connections are returned properly.

4. **Monitor Regularly**: Set up scheduled health checks (every 30-60 seconds) for continuous monitoring.

5. **Log Results**: Log health check results for troubleshooting and trend analysis.

6. **Set Up Alerts**: Use the health summary to trigger alerts when status changes to 'degraded' or 'unhealthy'.

## Response Structure

### `check_health()` Response

```python
{
    'status': str,              # 'healthy' or 'unhealthy'
    'database_type': str,       # Database type checked
    'response_time_ms': float,  # Response time in milliseconds
    'error': str | None,        # Error message if unhealthy
    'timestamp': float          # Unix timestamp
}
```

### `get_health_summary()` Response

```python
{
    'overall_status': str,      # 'healthy', 'degraded', or 'unhealthy'
    'databases': dict,           # Dictionary of individual results
    'healthy_count': int,        # Number of healthy databases
    'total_count': int,          # Total number of databases
    'timestamp': float           # Unix timestamp
}
```

## Notes

- The health checker uses the connection pool, so it's efficient and doesn't create unnecessary connections.
- All database types are automatically discovered from your configuration.
- The timeout parameter controls the maximum time allowed for the health check to complete.
- Response times include connection establishment, query execution, and cleanup.
