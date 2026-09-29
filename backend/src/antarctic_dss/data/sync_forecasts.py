"""Download a 10-day environmental forecast for the Antarctic into the API's Zarr cache.

    python src/antarctic_dss/data/sync_forecasts.py   (from backend/, with PYTHONPATH=src)

Variables on the Copernicus GLO12 grid (1/12 degree, daily, 80S-55S):
  siconc, sithick, usi, vsi   sea ice (Copernicus physics forecast)
  uo, vo                      surface currents (Copernicus currents forecast)
  swh                         daily max significant wave height (Copernicus wave forecast)
  wind_u, wind_v              10 m wind (ECMWF open-data IFS forecast; synthetic fallback)
"""
import sys
from pathlib import Path
import datetime

# Add src to path
sys.path.append(str(Path(__file__).parent.parent.parent))

import numpy as np
import xarray as xr

from antarctic_dss.data.copernicus import open_dataset_remote

FORECAST_DAYS = 10
LAT_SLICE = slice(-80, -55)

def _on_grid(ds: xr.Dataset, grid: xr.Dataset) -> xr.Dataset:
    """Nearest-neighbour regrid onto the forecast grid (lat/lon within one cell, time within 12 h)."""
    ds = ds.sortby('latitude').sortby('longitude')
    ds = ds.reindex(latitude=grid['latitude'], longitude=grid['longitude'], method='nearest', tolerance=0.3)
    return ds.reindex(time=grid['time'], method='nearest', tolerance=np.timedelta64(12, 'h'))

def _surface_currents(start_date: str, end_date: str, grid: xr.Dataset) -> xr.Dataset:
    currents = open_dataset_remote('ocean_currents_forecast', start_date, end_date)
    currents = currents.sel(latitude=LAT_SLICE)[['uo', 'vo']]
    if 'depth' in currents.dims:
        currents = currents.isel(depth=0, drop=True)
    return _on_grid(currents, grid)

def _waves(start_date: str, end_date: str, grid: xr.Dataset) -> xr.Dataset:
    waves = open_dataset_remote('wave_forecast', start_date, end_date)
    # 3-hourly -> daily maximum, the conservative value for route safety.
    swh = waves['VHM0'].sel(latitude=LAT_SLICE).resample(time='1D').max().rename('swh')
    return _on_grid(swh.to_dataset(), grid)

def _ecmwf_wind(grid: xr.Dataset, cache_dir: Path) -> xr.Dataset:
    """Latest 00 UTC ECMWF IFS 10 m wind (free open data, 0.25 degree), daily steps."""
    from ecmwf.opendata import Client

    target = cache_dir / 'ecmwf_wind.grib2'
    steps = list(range(0, 24 * FORECAST_DAYS + 1, 24))
    Client(source='ecmwf').retrieve(type='fc', time=0, param=['10u', '10v'], step=steps, target=str(target))
    wind = xr.open_dataset(target, engine='cfgrib', backend_kwargs={'indexpath': ''})
    wind = wind.assign_coords(time=wind['valid_time']).swap_dims({'step': 'time'})
    wind = wind[['u10', 'v10']].rename(u10='wind_u', v10='wind_v')
    wind = wind.drop_vars([c for c in wind.coords if c not in ('time', 'latitude', 'longitude')])
    wind['longitude'] = ((wind['longitude'] + 180) % 360) - 180
    return _on_grid(wind.load(), grid)

def _synthetic_wind(grid: xr.Dataset) -> xr.Dataset:
    """Random placeholder wind, flagged so the API reports it as synthetic."""
    dims = ('time', 'latitude', 'longitude')
    shape = tuple(grid.sizes[d] for d in dims)
    coords = {d: grid[d] for d in dims}
    attrs = {'synthetic': 1, 'comment': 'Random N(5,2)/N(-2,1.5) m/s placeholder, not a forecast'}
    return xr.Dataset({
        'wind_u': xr.DataArray(np.random.normal(5.0, 2.0, shape).astype(np.float32), coords=coords, dims=dims, attrs=attrs),
        'wind_v': xr.DataArray(np.random.normal(-2.0, 1.5, shape).astype(np.float32), coords=coords, dims=dims, attrs=attrs),
    })

STEPS = ['Sea ice forecast', 'Surface currents', 'Waves', 'ECMWF wind', 'Merging', 'Writing cache']

def _step(n: int):
    """Overall progress line, e.g. [###---] Step 3/6: Waves"""
    done = '#' * (n - 1) + '-' * (len(STEPS) - n + 1)
    print(f"\n[{done}] Step {n}/{len(STEPS)}: {STEPS[n - 1]}...", flush=True)

def sync_forecasts():
    from antarctic_dss.config import FORECAST_ZARR as output_zarr
    output_zarr.parent.mkdir(parents=True, exist_ok=True)

    now = datetime.datetime.now(datetime.timezone.utc)
    start_date = now.strftime('%Y-%m-%d')
    end_date = (now + datetime.timedelta(days=FORECAST_DAYS)).strftime('%Y-%m-%d')

    import logging
    logging.getLogger('copernicusmarine').setLevel(logging.WARNING)  # hide chatty INFO logs
    print(f"Refreshing {FORECAST_DAYS}-day Antarctic forecast ({start_date} to {end_date})")
    _step(1)
    ds = open_dataset_remote('ocean_forecast', start_date, end_date)
    subset = ds.sel(latitude=LAT_SLICE)
    keep = ['siconc', 'sithick', 'usi', 'vsi']
    subset = subset.drop_vars([v for v in subset.data_vars if v not in keep])
    grid = subset[['time', 'latitude', 'longitude']]

    parts = [subset]
    for step, (name, loader) in enumerate([('surface currents (uo, vo)', lambda: _surface_currents(start_date, end_date, grid)),
                         ('waves (swh)', lambda: _waves(start_date, end_date, grid))], start=2):
        _step(step)
        try:
            parts.append(loader())
            print(f"Added {name}.")
        except Exception as e:
            print(f"Warning: {name} unavailable, continuing without: {e}")

    wind_is_synthetic = 0
    _step(4)
    try:
        parts.append(_ecmwf_wind(grid, output_zarr.parent))
        print("Added ECMWF 10 m wind forecast.")
    except Exception as e:
        print(f"Warning: ECMWF wind unavailable ({e}); using SYNTHETIC placeholder wind.")
        parts.append(_synthetic_wind(grid))
        wind_is_synthetic = 1

    _step(5)
    merged = xr.merge(parts, compat='override', join='left')
    merged.attrs.update(synced_at=now.isoformat(), wind_is_synthetic=wind_is_synthetic,
                        forecast_days=FORECAST_DAYS)

    # Re-chunk to avoid Dask warnings about mismatched chunks
    merged = merged.chunk({'time': 1, 'latitude': 250, 'longitude': 250})
    # Clear encodings to avoid Zarr 3.x codec errors with Blosc
    for v in merged.variables:
        merged[v].encoding.clear()
    merged = merged.drop_vars([c for c in merged.coords if c not in merged.dims])

    # Write to a temporary store and swap it in, so a failed sync never destroys the old cache.
    import shutil
    tmp_zarr = output_zarr.with_name(output_zarr.name + '.tmp')
    _step(6)
    from dask.diagnostics import ProgressBar
    with ProgressBar(dt=1.0):  # percentage bar: downloading + writing is the slow part
        merged.to_zarr(tmp_zarr, mode='w', consolidated=True)
    if output_zarr.exists():
        shutil.rmtree(output_zarr)
    tmp_zarr.rename(output_zarr)
    print(f"\n[{'#' * len(STEPS)}] Done. Cached {FORECAST_DAYS}-day forecast ({', '.join(merged.data_vars)}) to {output_zarr}")

if __name__ == '__main__':
    sync_forecasts()
