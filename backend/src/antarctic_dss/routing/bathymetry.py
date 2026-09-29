"""Sea-floor depth on the routing grid, from the GLO12 model bathymetry (deptho).

Download once with `python scripts/download_copernicus.py --dataset bathymetry`.
"""
from functools import lru_cache
from typing import Optional, Tuple

import numpy as np

from antarctic_dss.config import RAW_DIR

BATHYMETRY_FILE = RAW_DIR / 'bathymetry' / 'deptho_southern_ocean.nc'

@lru_cache(maxsize=1)
def _load_depth() -> Optional[Tuple[np.ndarray, np.ndarray, np.ndarray]]:
    if not BATHYMETRY_FILE.exists():
        return None
    import xarray as xr
    with xr.open_dataset(BATHYMETRY_FILE) as ds:
        da = ds['deptho'].squeeze(drop=True)
        # NaN = land / ice shelf in the model: zero depth, so it's never traversable.
        depth = np.nan_to_num(da.values.astype(np.float32), nan=0.0)
        return da['latitude'].values, da['longitude'].values, depth

def depth_on_grid(lat_grid: np.ndarray, lon_grid: np.ndarray, cell_deg: float) -> Optional[np.ndarray]:
    """Shallowest depth (m) within ~half a routing cell of each grid point, or None if no data.

    Taking the minimum (not the mean or nearest value) keeps narrow shoals from being
    averaged away at coarse routing resolution. Rows outside the data's latitude range are NaN.
    """
    from scipy.ndimage import minimum_filter

    loaded = _load_depth()
    if loaded is None:
        return None
    lats, lons, depth = loaded
    step = abs(float(lats[1] - lats[0]))
    size = max(1, int(round(cell_deg / 2 / step))) | 1  # odd window, ~half a cell wide
    shallowest = minimum_filter(depth, size=size, mode=('nearest', 'wrap'))

    lat_order = np.argsort(lats)
    lat_idx = lat_order[np.clip(np.searchsorted(lats[lat_order], lat_grid), 0, len(lats) - 1)]
    lon_idx = np.clip(np.searchsorted(lons, ((lon_grid + 180.0) % 360.0) - 180.0), 0, len(lons) - 1)
    result = shallowest[np.ix_(lat_idx, lon_idx)].astype(float)

    outside = (lat_grid < lats.min() - step) | (lat_grid > lats.max() + step)
    result[outside, :] = np.nan
    return result

def depth_at_points(lats: np.ndarray, lons: np.ndarray) -> Optional[np.ndarray]:
    """Nearest model sea-floor depth (m) at each point (0 on land), or None without data."""
    loaded = _load_depth()
    if loaded is None:
        return None
    grid_lats, grid_lons, depth = loaded
    order = np.argsort(grid_lats)
    li = order[np.clip(np.searchsorted(grid_lats[order], lats), 0, len(grid_lats) - 1)]
    lj = np.clip(np.searchsorted(grid_lons, ((np.asarray(lons) + 180.0) % 360.0) - 180.0), 0, len(grid_lons) - 1)
    out = depth[li, lj].astype(float)
    out[(lats < grid_lats.min()) | (lats > grid_lats.max())] = np.nan
    return out
