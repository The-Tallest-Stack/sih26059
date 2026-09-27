"""Geospatial utilities for the Antarctic Voyage Decision Support System."""

import math
from pyproj import Transformer

def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Calculate the great circle distance between two points on the earth.
    
    Args:
        lat1: Latitude of the first point.
        lon1: Longitude of the first point.
        lat2: Latitude of the second point.
        lon2: Longitude of the second point.
        
    Returns:
        float: Distance in kilometers.
    """
    R = 6371.0 # Earth radius in kilometers

    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    
    a = math.sin(dlat / 2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    
    return R * c

def epsg4326_to_epsg3031(lon: float, lat: float) -> tuple[float, float]:
    """
    Convert EPSG:4326 (WGS 84) coordinates to EPSG:3031 (Antarctic Polar Stereographic).
    
    Args:
        lon: Longitude in EPSG:4326.
        lat: Latitude in EPSG:4326.
        
    Returns:
        tuple[float, float]: The (x, y) coordinates in EPSG:3031.
    """
    transformer = Transformer.from_crs("EPSG:4326", "EPSG:3031", always_xy=True)
    x, y = transformer.transform(lon, lat)
    return x, y

def epsg3031_to_epsg4326(x: float, y: float) -> tuple[float, float]:
    """
    Convert EPSG:3031 (Antarctic Polar Stereographic) coordinates to EPSG:4326 (WGS 84).
    
    Args:
        x: X coordinate in EPSG:3031.
        y: Y coordinate in EPSG:3031.
        
    Returns:
        tuple[float, float]: The (lon, lat) coordinates in EPSG:4326.
    """
    transformer = Transformer.from_crs("EPSG:3031", "EPSG:4326", always_xy=True)
    lon, lat = transformer.transform(x, y)
    return lon, lat

def bearing(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Calculate the initial bearing from point 1 to point 2.
    
    Args:
        lat1: Latitude of the first point.
        lon1: Longitude of the first point.
        lat2: Latitude of the second point.
        lon2: Longitude of the second point.
        
    Returns:
        float: Initial compass bearing in degrees.
    """
    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    dlon = math.radians(lon2 - lon1)

    x = math.sin(dlon) * math.cos(lat2_rad)
    y = math.cos(lat1_rad) * math.sin(lat2_rad) - (math.sin(lat1_rad) * math.cos(lat2_rad) * math.cos(dlon))

    initial_bearing = math.atan2(x, y)
    
    # Normalize to 0-360
    initial_bearing = math.degrees(initial_bearing)
    compass_bearing = (initial_bearing + 360) % 360

    return compass_bearing
