import calendar
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

import copernicusmarine
from antarctic_dss.config import settings
import xarray as xr

# Login using settings
if settings.COPERNICUS_USERNAME and settings.COPERNICUS_PASSWORD:
    copernicusmarine.login(
        username=settings.COPERNICUS_USERNAME,
        password=settings.COPERNICUS_PASSWORD
    )

@dataclass
class CopernicusDatasetConfig:
    dataset_id: str
    variables: List[str]
    regime: str  # 'historical' | 'nrt' | 'forecast'
    spatial_bounds: Optional[Dict[str, float]] = None
    depth_range: Optional[Dict[str, float]] = None

DATASET_CONFIGS = {
    'seaice_drift_reprocessed': CopernicusDatasetConfig(
        dataset_id='cmems_obs-si_ant_physic_my_drift-amsr_P2D',
        variables=['eastward_sea_ice_velocity', 'northward_sea_ice_velocity'],
        regime='historical'
    ),
    'ocean_reanalysis': CopernicusDatasetConfig(
        dataset_id='cmems_mod_glo_phy_my_0.083deg_P1D-m',
        variables=['uo', 'vo'],
        regime='historical',
        spatial_bounds=dict(min_lat=-80, max_lat=-50, min_lon=-180, max_lon=180),
        # Surface level only (0.494 m): training uses surface currents, and the full
        # 0.5-15 m range is ~9x larger (~20 GB/year).
        depth_range=dict(min=0.4, max=0.6)
    ),
    # Sea-ice concentration and velocity from the same GLORYS reanalysis, matching the
    # variables the live forecast (ocean_forecast) provides at inference time.
    'seaice_reanalysis': CopernicusDatasetConfig(
        dataset_id='cmems_mod_glo_phy_my_0.083deg_P1D-m',
        variables=['siconc', 'usi', 'vsi'],
        regime='historical',
        spatial_bounds=dict(min_lat=-80, max_lat=-50, min_lon=-180, max_lon=180),
    ),
    'seaice_nrt': CopernicusDatasetConfig(
        dataset_id='cmems_obs-si_ant_phy_nrt_l3-1km_P1D',
        variables=['ice_concentration', 'confidence'],
        regime='nrt'
    ),
    'ocean_forecast': CopernicusDatasetConfig(
        dataset_id='cmems_mod_glo_phy_anfc_0.083deg_P1D-m',
        variables=['siconc', 'sithick', 'usi', 'vsi'],
        regime='forecast',
        spatial_bounds=dict(min_lat=-90, max_lat=-50, min_lon=-180, max_lon=180),
        depth_range=dict(min=0.5, max=15.0)
    ),
    'ocean_currents_forecast': CopernicusDatasetConfig(
        dataset_id='cmems_mod_glo_phy-cur_anfc_0.083deg_P1D-m',
        variables=['uo', 'vo'],
        regime='forecast',
        spatial_bounds=dict(min_lat=-90, max_lat=-50, min_lon=-180, max_lon=180),
        depth_range=dict(min=0.5, max=1.0)
    ),
    'wave_forecast': CopernicusDatasetConfig(
        dataset_id='cmems_mod_glo_wav_anfc_0.083deg_PT3H-i',
        variables=['VHM0'],
        regime='forecast',
        spatial_bounds=dict(min_lat=-80, max_lat=-50, min_lon=-180, max_lon=180),
    ),
    'seaice_drift_nrt': CopernicusDatasetConfig(
        dataset_id='cmems_sat-si_glo_drift_nrt_south_d',
        variables=['dX', 'dY'],
        regime='nrt'
    )
}

def download_dataset(config_name: str, start_date: str, end_date: str, output_dir: Path) -> Path:
    """
    Downloads dataset using copernicusmarine subsetting, handling spatial boundaries.
    """
    config = DATASET_CONFIGS[config_name]
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / f"{config_name}_{start_date}_{end_date}.nc"
    
    kwargs = {
        "dataset_id": config.dataset_id,
        "variables": config.variables,
        "start_datetime": start_date,
        "end_datetime": end_date,
        "output_filename": output_file.name,
        "output_directory": str(output_dir),
        "force_download": True,
    }
    
    if config.spatial_bounds:
        kwargs.update({
            "minimum_latitude": config.spatial_bounds['min_lat'],
            "maximum_latitude": config.spatial_bounds['max_lat'],
            "minimum_longitude": config.spatial_bounds['min_lon'],
            "maximum_longitude": config.spatial_bounds['max_lon']
        })
    if config.depth_range:
        kwargs.update({
            "minimum_depth": config.depth_range['min'],
            "maximum_depth": config.depth_range['max']
        })

    copernicusmarine.subset(**kwargs)
    return output_file

def open_dataset_remote(config_name: str, start_date: str, end_date: str) -> xr.Dataset:
    """
    Opens dataset remotely via lazy loading.
    """
    config = DATASET_CONFIGS[config_name]
    ds = copernicusmarine.open_dataset(dataset_id=config.dataset_id)
    # Simple temporal slicing, assumes standard time coordinate naming
    return ds.sel(time=slice(start_date, end_date))

BATHYMETRY_DATASET_ID = 'cmems_mod_glo_phy_anfc_0.083deg_static'
BATHYMETRY_FILENAME = 'deptho_southern_ocean.nc'

def download_bathymetry(output_dir: Path) -> Path:
    """Download the GLO12 model sea-floor depth (deptho, metres) south of 50S."""
    output_dir.mkdir(parents=True, exist_ok=True)
    copernicusmarine.subset(
        dataset_id=BATHYMETRY_DATASET_ID,
        dataset_part='bathy',
        variables=['deptho'],
        minimum_latitude=-90, maximum_latitude=-50,
        minimum_longitude=-180, maximum_longitude=180,
        output_filename=BATHYMETRY_FILENAME,
        output_directory=str(output_dir),
    )
    return output_dir / BATHYMETRY_FILENAME

def download_historical_range(config_name: str, start_year: int, end_year: int, output_dir: Path, chunk_months: int = 1) -> List[Path]:
    """
    Downloads historical dataset in monthly chunks.
    """
    downloaded_files = []
    output_dir.mkdir(parents=True, exist_ok=True)
    
    for year in range(start_year, end_year + 1):
        for month in range(1, 13, chunk_months):
            start_date = f"{year}-{month:02d}-01"
            _, last_day = calendar.monthrange(year, month)
            end_date = f"{year}-{month:02d}-{last_day}"
            
            print(f"Downloading {config_name} chunk: {start_date} to {end_date}")
            try:
                out_path = download_dataset(config_name, start_date, end_date, output_dir)
                downloaded_files.append(out_path)
            except Exception as e:
                print(f"Failed to download {config_name} for {start_date}: {e}")
                
    return downloaded_files
