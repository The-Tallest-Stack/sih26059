import datetime
from pathlib import Path
from typing import List, Optional

import cdsapi
import xarray as xr

ERA5_VARIABLES = [
    '10m_u_component_of_wind',
    '10m_v_component_of_wind',
    'significant_height_of_combined_wind_waves_and_swell',
    'mean_wave_direction',
    'mean_wave_period',
    '2m_temperature',
    'mean_sea_level_pressure'
]

ANTARCTIC_AREA = [-50, -180, -90, 180]  # [N, W, S, E]
TIMES_6HOURLY = ['00:00', '06:00', '12:00', '18:00']

def download_era5_monthly(year: int, month: int, output_dir: Path, variables: Optional[List[str]] = None) -> Path:
    """
    Download one month of ERA5 data. ERA5 is a reanalysis dataset, NOT a forecast, 
    so it provides historical atmospheric and wave conditions.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    filename = f"era5_antarctic_{year}{month:02d}.nc"
    output_path = output_dir / filename
    
    if output_path.exists():
        print(f"File {output_path} already exists. Skipping download.")
        return output_path

    if variables is None:
        variables = ERA5_VARIABLES

    c = cdsapi.Client()
    
    # We download 6-hourly data for the entire month over the Antarctic area
    request = {
        'product_type': 'reanalysis',
        'format': 'netcdf',
        'variable': variables,
        'year': str(year),
        'month': f"{month:02d}",
        'day': [f"{d:02d}" for d in range(1, 32)],
        'time': TIMES_6HOURLY,
        'area': ANTARCTIC_AREA,
    }

    print(f"Downloading ERA5 for {year}-{month:02d} to {output_path}...")
    c.retrieve('reanalysis-era5-single-levels', request, str(output_path))
    return output_path

WIND_VARIABLES = ['10m_u_component_of_wind', '10m_v_component_of_wind']

def download_era5_wind_year(year: int, output_dir: Path) -> Path:
    """
    Download one year of 6-hourly 10 m wind (all the training pipeline uses) in a single CDS
    request, unpacked to era5_wind_{year}_unzipped/data_stream-oper_stepType-instant.nc so it
    matches the layout of the monthly downloads.
    """
    import shutil
    import zipfile

    output_dir.mkdir(parents=True, exist_ok=True)
    unzipped_dir = output_dir / f"era5_wind_{year}_unzipped"
    final = unzipped_dir / "data_stream-oper_stepType-instant.nc"
    if final.exists() and final.stat().st_size > 0:
        print(f"{final} already exists. Skipping download.")
        return final

    download_path = output_dir / f"era5_wind_{year}.part"
    request = {
        'product_type': 'reanalysis',
        'format': 'netcdf',
        'variable': WIND_VARIABLES,
        'year': str(year),
        'month': [f"{m:02d}" for m in range(1, 13)],
        'day': [f"{d:02d}" for d in range(1, 32)],
        'time': TIMES_6HOURLY,
        'area': ANTARCTIC_AREA,
    }
    print(f"Requesting ERA5 10 m wind for {year} (one CDS request)...")
    cdsapi.Client().retrieve('reanalysis-era5-single-levels', request, str(download_path))

    unzipped_dir.mkdir(parents=True, exist_ok=True)
    if zipfile.is_zipfile(download_path):
        with zipfile.ZipFile(download_path) as z:
            z.extractall(unzipped_dir)
        download_path.unlink()
        if not final.exists():
            # Single-stream zips may use another name: normalise it.
            ncs = sorted(unzipped_dir.glob('*.nc'))
            if len(ncs) == 1:
                ncs[0].rename(final)
    else:
        shutil.move(str(download_path), str(final))
    return final

def download_era5_range(start_year: int, end_year: int, output_dir: Path) -> List[Path]:
    """
    Downloads ERA5 reanalysis data over a specified range of years, iterating by month.
    """
    files = []
    for year in range(start_year, end_year + 1):
        for month in range(1, 13):
            file_path = download_era5_monthly(year, month, output_dir)
            files.append(file_path)
    return files

def open_era5(file_path: Path) -> xr.Dataset:
    """
    Open ERA5 dataset using xarray, renaming coordinate variables if needed for consistency.
    """
    ds = xr.open_dataset(file_path)
    
    # Optional renaming mapping for consistency with other datasets
    rename_vars = {}
    if 'longitude' in ds.coords:
        rename_vars['longitude'] = 'lon'
    if 'latitude' in ds.coords:
        rename_vars['latitude'] = 'lat'
        
    if rename_vars:
        ds = ds.rename(rename_vars)
        
    return ds
