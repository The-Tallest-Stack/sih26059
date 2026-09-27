import os
from pathlib import Path
import logging

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)

def main():
    \"\"\"Print instructions on how to manually download GEBCO bathymetry subset.\"\"\"
    # Default path assuming standard structure
    project_root = Path(__file__).resolve().parent.parent
    gebco_dir = project_root / 'data' / 'raw' / 'gebco'
    
    # Check if a .nc file exists in the directory
    nc_files = list(gebco_dir.glob('*.nc')) if gebco_dir.exists() else []
    
    if nc_files:
        logger.info(f"GEBCO data found: {nc_files[0]}")
    else:
        logger.info("=== GEBCO Bathymetry Data Required ===")
        logger.info("The GEBCO bathymetry data must be downloaded manually.")
        logger.info("\nInstructions:")
        logger.info("1. Visit: https://download.gebco.net/")
        logger.info("2. Use the map interface to select the Southern Ocean / Antarctica bounding box.")
        logger.info("   Suggested bounds: South: -90, North: -50, West: -180, East: 180")
        logger.info("3. Select '2D netCDF' format and download.")
        logger.info("4. Extract the downloaded zip and place the .nc file into:")
        logger.info(f"   {gebco_dir}")
        logger.info("\nOnce placed, the system will be able to process ocean depths.")

if __name__ == '__main__':
    main()
