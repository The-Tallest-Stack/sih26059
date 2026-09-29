from pathlib import Path
from typing import Any, List

import earthaccess
import xarray as xr

def search_g02202(start_date: str, end_date: str, hemisphere: str = 'south') -> List[Any]:
    """
    Search for G02202 granules using earthaccess. Filter filenames containing '_sh_'
    for the Southern Hemisphere.
    """
    import os
    from antarctic_dss.config import settings
    os.environ['EARTHDATA_USERNAME'] = settings.EARTHDATA_USERNAME
    os.environ['EARTHDATA_PASSWORD'] = settings.EARTHDATA_PASSWORD
    earthaccess.login(strategy="environment")
    results = earthaccess.search_data(
        short_name='G02202',
        temporal=(start_date, end_date)
    )
    
    # Filter for specific hemisphere if needed
    if hemisphere == 'south':
        filtered = [res for res in results if '_sh_' in res['umm']['DataGranule']['Identifiers'][0]['Identifier']]
        return filtered
    return results

def download_g02202(start_date: str, end_date: str, output_dir: Path) -> List[Path]:
    """
    Search and download G02202 data.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    granules = search_g02202(start_date, end_date, hemisphere='south')
    
    print(f"Found {len(granules)} granules for G02202 in {start_date} to {end_date}.")
    downloaded_paths = earthaccess.download(granules, str(output_dir))
    
    return [Path(p) for p in downloaded_paths]

def open_g02202(file_paths: List[Path]) -> xr.Dataset:
    """
    Open multiple G02202 netCDF files with xr.open_mfdataset.
    Key variable is 'cdr_seaice_conc'.
    """
    ds = xr.open_mfdataset([str(p) for p in file_paths], combine='by_coords')
    return ds
