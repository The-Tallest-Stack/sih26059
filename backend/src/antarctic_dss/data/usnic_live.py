import io
from datetime import datetime, timedelta, timezone
from typing import Any, Dict

import httpx
import pandas as pd
import geopandas as gpd
from pathlib import Path
from shapely.geometry import Point

USNIC_CSV_URL = "https://usicecenter.gov/pub/Iceberg_Tabular.csv"
FETCH_TIMEOUT_S = 20.0
CACHE_TTL = timedelta(minutes=30)

# Module-level cache shared by all API requests (USNIC updates the table about weekly).
_cache: Dict[str, Any] = {'gdf': None, 'fetched_at': None, 'last_error': None, 'last_attempt': None}

def _download_icebergs() -> gpd.GeoDataFrame:
    response = httpx.get(USNIC_CSV_URL, timeout=FETCH_TIMEOUT_S, follow_redirects=True)
    response.raise_for_status()
    df = pd.read_csv(io.StringIO(response.content.decode('utf-8-sig')))
    # Make sure we keep the Iceberg name column clean
    if 'Iceberg' not in df.columns and len(df.columns) > 0:
        # If there's a weird character, rename the first column
        df.rename(columns={df.columns[0]: 'Iceberg'}, inplace=True)

    geometry = [Point(xy) for xy in zip(df['Longitude'], df['Latitude'])]
    gdf = gpd.GeoDataFrame(df, geometry=geometry, crs="EPSG:4326")
    gdf['geom_3031'] = gdf.geometry.to_crs("EPSG:3031")
    return gdf

def fetch_current_icebergs(max_age: timedelta = CACHE_TTL) -> gpd.GeoDataFrame:
    """
    Fetch the USNIC iceberg CSV and parse it into a GeoDataFrame (cached for max_age).

    If a refresh fails but an earlier fetch succeeded, the stale copy is returned (see
    fetch_status() for its age); if no copy exists, the error is raised.

    Returns:
        gpd.GeoDataFrame: A GeoDataFrame in EPSG:4326 with additional EPSG:3031 projected geometry.
    """
    now = datetime.now(timezone.utc)
    fetched_at = _cache['fetched_at']
    if _cache['gdf'] is not None and fetched_at is not None and now - fetched_at < max_age:
        return _cache['gdf'].copy()

    _cache['last_attempt'] = now
    try:
        gdf = _download_icebergs()
    except Exception as e:
        _cache['last_error'] = str(e)
        if _cache['gdf'] is not None:
            return _cache['gdf'].copy()
        raise
    _cache.update(gdf=gdf, fetched_at=now, last_error=None)
    return gdf.copy()

def fetch_status() -> Dict[str, Any]:
    """When icebergs were last fetched successfully, and the last error (if any)."""
    return {k: _cache[k] for k in ('fetched_at', 'last_attempt', 'last_error')}

def create_exclusion_zones(gdf: gpd.GeoDataFrame, buffer_nm: float = 3.0) -> gpd.GeoDataFrame:
    """
    Project to EPSG:3031 and create exclusion zones.
    
    Args:
        gdf (gpd.GeoDataFrame): GeoDataFrame containing iceberg locations.
        buffer_nm (float): Additional buffer in nautical miles.
        
    Returns:
        gpd.GeoDataFrame: GeoDataFrame with polygon geometries for exclusion zones in EPSG:3031.
    """
    gdf_3031 = gdf.copy()
    gdf_3031.geometry = gdf_3031.geometry.to_crs("EPSG:3031")
    
    max_dim = gdf_3031[['Length (NM)', 'Width (NM)']].max(axis=1)
    buffer_meters = (max_dim / 2 + buffer_nm) * 1852.0
    
    gdf_3031.geometry = gdf_3031.geometry.buffer(buffer_meters)
    return gdf_3031

def export_geojson(gdf: gpd.GeoDataFrame, output_path: Path) -> Path:
    """
    Export the GeoDataFrame to a GeoJSON file.
    
    Args:
        gdf (gpd.GeoDataFrame): GeoDataFrame to export.
        output_path (Path): Path to the output GeoJSON file.
        
    Returns:
        Path: Path to the written file.
    """
    gdf_4326 = gdf.to_crs("EPSG:4326")
    gdf_4326.to_file(output_path, driver="GeoJSON")
    return output_path
