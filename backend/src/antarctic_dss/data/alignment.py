from typing import Any, Dict, List, Optional, Union
import numpy as np
import pandas as pd
import xarray as xr
from pyproj import Transformer

WGS84_TO_3412 = Transformer.from_crs("EPSG:4326", "EPSG:3412", always_xy=True)
WGS84_TO_3031 = Transformer.from_crs("EPSG:4326", "EPSG:3031", always_xy=True)

def sample_latlon_grid(ds: xr.Dataset, lat: float, lon: float, time: Any, variables: List[str]) -> Dict[str, float]:
    """
    Sample a regular lat/lon gridded dataset at a point and time using nearest neighbor.
    Returns dict of variable name -> value.
    """
    try:
        if 'depth' in ds.coords:
            point_ds = ds.sel(lat=lat, lon=lon, time=time, method='nearest').isel(depth=0)
        else:
            point_ds = ds.sel(lat=lat, lon=lon, time=time, method='nearest')
        return {var: float(np.nanmean(point_ds[var].values)) if point_ds[var].values.ndim > 0 else float(point_ds[var].values) for var in variables}
    except KeyError:
        # Fallback if using full coordinate names (ERA5 uses latitude, longitude, and sometimes valid_time)
        time_coord = 'valid_time' if 'valid_time' in ds.coords else 'time'
        lat_coord = 'latitude' if 'latitude' in ds.coords else 'lat'
        lon_coord = 'longitude' if 'longitude' in ds.coords else 'lon'
        if 'depth' in ds.coords:
            point_ds = ds.sel({lat_coord: lat, lon_coord: lon, time_coord: time}, method='nearest').isel(depth=0)
        else:
            point_ds = ds.sel({lat_coord: lat, lon_coord: lon, time_coord: time}, method='nearest')
        return {var: float(np.nanmean(point_ds[var].values)) if point_ds[var].values.ndim > 0 else float(point_ds[var].values) for var in variables}
    except Exception:
        return {var: np.nan for var in variables}

def sample_polar_stereo_grid(ds: xr.Dataset, lat: float, lon: float, time: Any, variables: List[str], to_crs: str = 'EPSG:3412') -> Dict[str, float]:
    """
    Convert lat/lon to X/Y in specified CRS, then sample the grid using nearest neighbor.
    """
    try:
        if to_crs == 'EPSG:3412':
            x, y = WGS84_TO_3412.transform(lon, lat)
        elif to_crs == 'EPSG:3031':
            x, y = WGS84_TO_3031.transform(lon, lat)
        else:
            transformer = Transformer.from_crs("EPSG:4326", to_crs, always_xy=True)
            x, y = transformer.transform(lon, lat)
            
        point_ds = ds.sel(x=x, y=y, time=time, method='nearest')
        return {var: float(point_ds[var].values) for var in variables}
    except Exception:
        return {var: np.nan for var in variables}

def build_training_row(iceberg_obs: Union[Dict, pd.Series], env_datasets: Dict[str, xr.Dataset]) -> Dict[str, Any]:
    """
    Build one training row by extracting iceberg fields and sampling environmental datasets.
    env_datasets dict expects keys like 'era5', 'ocean', 'seaice_conc', 'seaice_drift'.
    """
    lat = iceberg_obs['lat']
    lon = iceberg_obs['lon']
    time = iceberg_obs['timestamp']
    
    row = {
        'iceberg_id': iceberg_obs.get('iceberg_id'),
        'timestamp': time,
        'lat': lat,
        'lon': lon,
        'x_3031': iceberg_obs.get('x_3031'),
        'y_3031': iceberg_obs.get('y_3031'),
        'size': iceberg_obs.get('size'),
        'disp': iceberg_obs.get('disp'),
        'mask': iceberg_obs.get('mask'),
        'target_dx': iceberg_obs.get('target_dx', np.nan),
        'target_dy': iceberg_obs.get('target_dy', np.nan),
    }

    # Sample ERA5
    if 'era5' in env_datasets:
        # CDS usually returns u10 and v10
        era5_vars = ['u10', 'v10']
        era5_data = sample_latlon_grid(env_datasets['era5'], lat, lon, time, era5_vars)
        row['wind_u'] = era5_data.get('u10', np.nan)
        row['wind_v'] = era5_data.get('v10', np.nan)

    # Sample Ocean
    if 'ocean' in env_datasets:
        ocean_vars = ['uo', 'vo']
        ocean_data = sample_latlon_grid(env_datasets['ocean'], lat, lon, time, ocean_vars)
        row['ocean_current_u'] = ocean_data.get('uo', np.nan)
        row['ocean_current_v'] = ocean_data.get('vo', np.nan)
        
    # Sample Sea Ice Concentration
    if 'seaice_conc' in env_datasets:
        si_conc_vars = ['ice_concentration'] # Adapt to dataset
        si_data = sample_polar_stereo_grid(env_datasets['seaice_conc'], lat, lon, time, si_conc_vars)
        row['seaice_concentration'] = si_data.get('ice_concentration', np.nan)

    # Sample Sea Ice Drift
    if 'seaice_drift' in env_datasets:
        si_drift_vars = ['eastward_sea_ice_velocity', 'northward_sea_ice_velocity']
        # The CMEMS Antarctic drift product used here is on a regular lat/lon grid.
        si_drift_data = sample_latlon_grid(env_datasets['seaice_drift'], lat, lon, time, si_drift_vars)
        row['seaice_drift_u'] = si_drift_data.get('eastward_sea_ice_velocity', np.nan)
        row['seaice_drift_v'] = si_drift_data.get('northward_sea_ice_velocity', np.nan)
        
    return row


# (dataset key, source variable, output column) for the vectorised sampler below.
ENV_VARIABLES = [
    ('era5', 'u10', 'wind_u'),
    ('era5', 'v10', 'wind_v'),
    ('ocean', 'uo', 'ocean_current_u'),
    ('ocean', 'vo', 'ocean_current_v'),
    ('seaice_drift', 'eastward_sea_ice_velocity', 'seaice_drift_u'),
    ('seaice_drift', 'northward_sea_ice_velocity', 'seaice_drift_v'),
    ('seaice_conc', 'ice_concentration', 'seaice_concentration'),
    # GLORYS reanalysis sea ice (preferred: the same variables the live forecast provides).
    ('seaice_model', 'siconc', 'seaice_concentration'),
    ('seaice_model', 'usi', 'seaice_drift_u'),
    ('seaice_model', 'vsi', 'seaice_drift_v'),
]

def _coord_name(ds: xr.Dataset, *candidates: str) -> str:
    for name in candidates:
        if name in ds.coords or name in ds.dims:
            return name
    raise KeyError(f"None of {candidates} found in dataset coordinates {list(ds.coords)}")

def _window_mean_field(ds: xr.Dataset, variables: List[str], start: pd.Timestamp, hours: float = 24.0) -> Optional[xr.Dataset]:
    """Mean of the given variables over [start, start + hours), surface level only, loaded in memory."""
    time_name = _coord_name(ds, 'valid_time', 'time')
    window = ds[variables].sel({time_name: slice(start, start + pd.Timedelta(hours=hours) - pd.Timedelta(seconds=1))})
    if window.sizes[time_name] == 0:
        return None
    if 'depth' in window.dims:
        window = window.isel(depth=0)
    return window.mean(time_name).load()

def sample_environment(obs: pd.DataFrame, env_datasets: Dict[str, xr.Dataset], window_hours: float = 24.0) -> pd.DataFrame:
    """
    Vectorised spatiotemporal alignment of iceberg observations with gridded forcing.

    For each observation at time t, every variable is averaged over the displacement window
    [t, t + window) and sampled at the nearest grid point. The window is the row's
    `gap_days` (time to the next fix) when present, else window_hours. Points outside a dataset's
    latitude coverage (where nearest-neighbour would silently clamp to the edge) get NaN.
    Observations are processed one day at a time so only a day of each dataset is in memory.
    """
    out = obs.copy()
    for _, _, column in ENV_VARIABLES:
        out[column] = np.nan

    days = out['timestamp'].dt.floor('D')
    if 'gap_days' in out.columns:
        windows = np.ceil(out['gap_days'].fillna(window_hours / 24.0)).clip(lower=1) * 24.0
    else:
        windows = pd.Series(window_hours, index=out.index)
    groups = out.groupby([days, windows]).groups
    for n, ((day, window), idx) in enumerate(groups.items(), start=1):
        if n % 50 == 0 or n == len(groups):
            print(f"  aligned {n}/{len(groups)} day-windows ({pd.Timestamp(day).date()})", flush=True)
        lats = out.loc[idx, 'lat'].values
        lons = out.loc[idx, 'lon'].values
        for key in dict.fromkeys(k for k, _, _ in ENV_VARIABLES):
            ds = env_datasets.get(key)
            if ds is None:
                continue
            specs = [(var, col) for k, var, col in ENV_VARIABLES if k == key and var in ds.data_vars]
            if not specs:
                continue
            field = _window_mean_field(ds, [v for v, _ in specs], pd.Timestamp(day), float(window))
            if field is None:
                continue
            lat_name = _coord_name(field, 'latitude', 'lat')
            lon_name = _coord_name(field, 'longitude', 'lon')
            points = field.sel({lat_name: xr.DataArray(lats, dims='p'), lon_name: xr.DataArray(lons, dims='p')}, method='nearest')

            grid_lats = field[lat_name].values
            step = abs(float(grid_lats[1] - grid_lats[0])) if len(grid_lats) > 1 else 0.0
            inside = (lats >= grid_lats.min() - step) & (lats <= grid_lats.max() + step)
            for var, col in specs:
                out.loc[idx, col] = np.where(inside, points[var].values, np.nan)
    return out
