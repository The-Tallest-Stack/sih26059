from pathlib import Path
from typing import Any

import geopandas as gpd
from shapely.ops import unary_union

def load_coastline(gpkg_path: Path) -> gpd.GeoDataFrame:
    """
    Load coastline polygon layer from a GeoPackage and ensure CRS is EPSG:3031.
    """
    gdf = gpd.read_file(gpkg_path)
    if gdf.crs != "EPSG:3031":
        gdf = gdf.to_crs("EPSG:3031")
    return gdf

def build_land_mask(coastline_gdf: gpd.GeoDataFrame) -> Any:
    """
    Create a unified impassable polygon using shapely unary_union.
    """
    unified_geom = unary_union(coastline_gdf.geometry)
    return unified_geom

def export_coastline_geojson(coastline_gdf: gpd.GeoDataFrame, output_path: Path) -> Path:
    """
    Convert coastline to EPSG:4326 and export as GeoJSON.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    reprojected = coastline_gdf.to_crs("EPSG:4326")
    reprojected.to_file(output_path, driver="GeoJSON")
    return output_path
