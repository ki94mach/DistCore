"""Date conversion utilities for pipelines."""

from datetime import date


def get_jalali_year(gregorian_date: date) -> int:
    """
    Calculate Jalali year from Gregorian date.
    
    Jalali (Persian) calendar year starts around March 21 (Gregorian).
    This is an approximate conversion that works well for years after 2000.
    
    Args:
        gregorian_date: Gregorian date to convert
        
    Returns:
        Jalali year as integer
        
    Example:
        >>> get_jalali_year(date(2024, 1, 15))
        1402
        >>> get_jalali_year(date(2024, 4, 1))
        1403
    """
    gregorian_year = gregorian_date.year
    gregorian_month = gregorian_date.month
    gregorian_day = gregorian_date.day
    
    # Jalali year starts around March 21 (Gregorian)
    # Adjust based on whether we're before or after March 21
    if gregorian_month < 3 or (gregorian_month == 3 and gregorian_day < 21):
        return gregorian_year - 622
    else:
        return gregorian_year - 621


def substitute_jalali_year_parameter(query: str, gregorian_date: date, parameter_name: str = 'current_jalali_year') -> str:
    """
    Substitute a Jalali year parameter placeholder in SQL query with actual calculated value.
    
    This is useful when SQL queries need to filter by the current Jalali year.
    The function calculates the Jalali year from the provided Gregorian date and
    replaces the placeholder (e.g., @current_jalali_year) with the numeric value.
    
    Args:
        query: SQL query with Jalali year parameter placeholder (e.g., @current_jalali_year)
        gregorian_date: Gregorian date to use for Jalali year calculation
        parameter_name: Name of the parameter to substitute (without @ prefix)
        
    Returns:
        Query with Jalali year parameter substituted with numeric value
        
    Example:
        >>> query = "SELECT * FROM table WHERE [Year] = @current_jalali_year"
        >>> substitute_jalali_year_parameter(query, date(2024, 4, 1))
        "SELECT * FROM table WHERE [Year] = 1403"
    """
    jalali_year = get_jalali_year(gregorian_date)
    return query.replace(f'@{parameter_name}', str(jalali_year))

