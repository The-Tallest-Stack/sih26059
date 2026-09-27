import os
from pathlib import Path
import logging

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)

def main():
    \"\"\"Print instructions on how to manually download SCAR ADD GeoPackage.\"\"\"
    # Default path assuming standard structure
    project_root = Path(__file__).resolve().parent.parent
    scar_add_dir = project_root / 'data' / 'raw' / 'scar_add'
    
    # Check if a .gpkg file exists in the directory
    gpkg_files = list(scar_add_dir.glob('*.gpkg')) if scar_add_dir.exists() else []
    
    if gpkg_files:
        logger.info(f"SCAR ADD data found: {gpkg_files[0]}")
    else:
        logger.info("=== SCAR Antarctic Digital Database (ADD) Data Required ===")
        logger.info("The SCAR ADD data must be downloaded manually due to licensing/access.")
        logger.info("\nInstructions:")
        logger.info("1. Visit: https://data.bas.ac.uk/")
        logger.info("2. Search for 'SCAR Antarctic Digital Database'")
        logger.info("3. Download the Coastline / High-resolution vector data (GeoPackage format).")
        logger.info("4. Place the downloaded .gpkg file into the following directory:")
        logger.info(f"   {scar_add_dir}")
        logger.info("\nOnce placed, the system will be able to process the high-resolution coastlines.")

if __name__ == '__main__':
    main()
