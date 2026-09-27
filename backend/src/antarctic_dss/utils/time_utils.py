"""Time and date utilities for the Antarctic Voyage Decision Support System."""

from datetime import datetime
import math

def yyyyddd_to_datetime(yyyyddd: int) -> datetime:
    """
    Convert year and day-of-year (YYYYDDD) to a datetime object.
    
    Args:
        yyyyddd: Integer representing the year and day of the year (e.g., 2023001).
        
    Returns:
        datetime: The corresponding datetime object.
    """
    return datetime.strptime(str(yyyyddd), "%Y%j")

def datetime_to_yyyyddd(dt: datetime) -> int:
    """
    Convert a datetime object to year and day-of-year (YYYYDDD).
    
    Args:
        dt: The datetime object.
        
    Returns:
        int: The year and day of the year (e.g., 2023001).
    """
    return int(dt.strftime("%Y%j"))

def cyclic_encode(value: float, period: float) -> tuple[float, float]:
    """
    Encode a cyclic feature (like day of year or hour of day) using sin and cos.
    
    Args:
        value: The current value in the cycle.
        period: The total period of the cycle.
        
    Returns:
        tuple[float, float]: The sine and cosine components.
    """
    angle = (2 * math.pi * value) / period
    return math.sin(angle), math.cos(angle)
