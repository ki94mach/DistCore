"""
Simple examples of using DatabaseHealthChecker

Run this file to see health checking in action:
    From project root: python -m src.orchestrator.services.health_check_example
"""

import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from src.orchestrator.services.db_health import DatabaseHealthChecker


def main():
    """Run health check examples."""
    
    print("=" * 60)
    print("Database Health Checker Examples")
    print("=" * 60)
    print()
    
    # Create health checker
    health_checker = DatabaseHealthChecker()
    
    # Example 1: Simple boolean check
    print("1. Simple Health Check (Boolean)")
    print("-" * 60)
    is_healthy = health_checker.is_healthy('source', timeout=5.0)
    if is_healthy:
        print("✅ Source database is healthy!")
    else:
        print("❌ Source database is unhealthy!")
    print()
    
    # Example 2: Detailed health check
    print("2. Detailed Health Check")
    print("-" * 60)
    result = health_checker.check_health('source', timeout=5.0)
    print(f"Status: {result['status']}")
    print(f"Response Time: {result['response_time_ms']} ms")
    if result['error']:
        print(f"Error: {result['error']}")
    print()
    
    # Example 3: Check all databases
    print("3. Check All Databases")
    print("-" * 60)
    all_results = health_checker.check_all_databases(timeout=5.0)
    for db_type, result in all_results.items():
        status_icon = "✅" if result['status'] == 'healthy' else "❌"
        print(f"{status_icon} {db_type}: {result['status']} "
              f"({result['response_time_ms']} ms)")
    print()
    
    # Example 4: Health summary
    print("4. Health Summary")
    print("-" * 60)
    summary = health_checker.get_health_summary(timeout=5.0)
    print(f"Overall Status: {summary['overall_status']}")
    print(f"Healthy Databases: {summary['healthy_count']}/{summary['total_count']}")
    print()
    
    print("=" * 60)
    print("Examples completed!")
    print("=" * 60)


if __name__ == "__main__":
    main()
