from dataclasses import dataclass
from pathlib import Path
import numpy as np
import xarray as xr

@dataclass
class BathymetryGrid:
    lats: np.ndarray
    lons: np.ndarray
    elevation: np.ndarray
    traversable_mask: np.ndarray
    cost_grid: np.ndarray

def load_gebco(nc_path: Path) -> xr.Dataset:
    """
    Open GEBCO NetCDF. Returns Dataset with 'elevation' variable.
    """
    return xr.open_dataset(nc_path)

def build_bathymetric_constraints(ds: xr.Dataset, vessel_draft_m: float = 7.5, ukc_margin_m: float = 2.0) -> BathymetryGrid:
    """
    Create traversability mask and cost grid.
    traversable = elevation <= -(draft+ukc).
    Cost grid uses exponential penalty as depth approaches minimum safe depth.
    """
    min_safe_depth = -(vessel_draft_m + ukc_margin_m)
    
    elevation = ds['elevation'].values
    lats = ds['lat'].values if 'lat' in ds.coords else ds['latitude'].values
    lons = ds['lon'].values if 'lon' in ds.coords else ds['longitude'].values
    
    traversable_mask = elevation <= min_safe_depth
    
    # Safe depths are negative. As elevation approaches min_safe_depth from below, penalty increases
    # E.g. elevation is -20, safe depth -10 -> difference is 10.
    depth_buffer = min_safe_depth - elevation 
    
    # Where not traversable, cost is infinity
    # Otherwise, apply exponential penalty for being close to the minimum safe depth
    cost_grid = np.where(
        traversable_mask,
        np.exp(10.0 / (depth_buffer + 1.0)),  # Avoid division by zero
        np.inf
    )
    
    return BathymetryGrid(
        lats=lats,
        lons=lons,
        elevation=elevation,
        traversable_mask=traversable_mask,
        cost_grid=cost_grid
    )
