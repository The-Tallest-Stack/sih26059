"""Geospatial utilities for the Antarctic Voyage Decision Support System."""

import math
import numpy as np
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

EARTH_RADIUS_M = 6371000.0

def wrap_lon(lon):
    """Wrap longitude(s) into [-180, 180). Works on floats and numpy arrays."""
    return (np.asarray(lon) + 180.0) % 360.0 - 180.0

def haversine_km_array(lat1, lon1, lat2, lon2):
    """Vectorised great-circle distance in km (numpy broadcasting)."""
    lat1, lon1, lat2, lon2 = (np.radians(np.asarray(v, dtype=float)) for v in (lat1, lon1, lat2, lon2))
    a = np.sin((lat2 - lat1) / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2) ** 2
    return 2 * 6371.0 * np.arcsin(np.sqrt(np.clip(a, 0.0, 1.0)))

def east_north_displacement_m(lat1, lon1, lat2, lon2):
    """Local tangent-plane (east, north) displacement in metres from point 1 to point 2.

    Handles the antimeridian. Accurate for the ~daily iceberg displacements (< 100 km)
    this is used for, and in the same east/north frame as wind/current u/v components.
    """
    lat1, lat2 = np.asarray(lat1, dtype=float), np.asarray(lat2, dtype=float)
    dlon = np.radians(wrap_lon(np.asarray(lon2, dtype=float) - np.asarray(lon1, dtype=float)))
    mean_lat = np.radians((lat1 + lat2) / 2.0)
    dx = EARTH_RADIUS_M * np.cos(mean_lat) * dlon
    dy = EARTH_RADIUS_M * np.radians(lat2 - lat1)
    return dx, dy

def apply_east_north_offset(lat: float, lon: float, dx_m: float, dy_m: float) -> tuple[float, float]:
    """Move a point by an (east, north) offset in metres. Returns (lat, lon)."""
    new_lat = lat + math.degrees(dy_m / EARTH_RADIUS_M)
    mean_lat = math.radians((lat + new_lat) / 2.0)
    cos_lat = max(math.cos(mean_lat), 1e-6)
    new_lon = float(wrap_lon(lon + math.degrees(dx_m / (EARTH_RADIUS_M * cos_lat))))
    return new_lat, new_lon

def great_circle_points(lat1: float, lon1: float, lat2: float, lon2: float, spacing_km: float = 10.0) -> list[tuple[float, float]]:
    """Sample points along the great circle between two points (inclusive), ~spacing_km apart."""
    dist = haversine_distance(lat1, lon1, lat2, lon2)
    n = max(2, int(math.ceil(dist / spacing_km)) + 1)
    p1 = np.radians([lat1, lon1])
    p2 = np.radians([lat2, lon2])
    v1 = np.array([math.cos(p1[0]) * math.cos(p1[1]), math.cos(p1[0]) * math.sin(p1[1]), math.sin(p1[0])])
    v2 = np.array([math.cos(p2[0]) * math.cos(p2[1]), math.cos(p2[0]) * math.sin(p2[1]), math.sin(p2[0])])
    omega = math.acos(float(np.clip(np.dot(v1, v2), -1.0, 1.0)))
    points = []
    for f in np.linspace(0.0, 1.0, n):
        if omega < 1e-12:
            v = v1
        else:
            v = (math.sin((1 - f) * omega) * v1 + math.sin(f * omega) * v2) / math.sin(omega)
        points.append((math.degrees(math.atan2(v[2], math.hypot(v[0], v[1]))), math.degrees(math.atan2(v[1], v[0]))))
    return points

def unwrap_lons(lons: list[float]) -> list[float]:
    """Make a longitude sequence continuous (e.g. 179 -> 181 instead of -179) for line rendering."""
    if not lons:
        return []
    out = [lons[0]]
    for lon in lons[1:]:
        prev = out[-1]
        out.append(prev + float(wrap_lon(lon - prev)))
    return out
