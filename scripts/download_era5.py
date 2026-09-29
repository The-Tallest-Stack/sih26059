import argparse
import sys
import logging
from pathlib import Path

# Add backend/src to path so we can import antarctic_dss
sys.path.append(str(Path(__file__).resolve().parent.parent / "backend" / "src"))

try:
    from antarctic_dss.data.era5 import download_era5_range
    from antarctic_dss.config import RAW_DIR
except ImportError as e:
    print(f"ImportError: {e}")
    download_era5_range = None

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def main():
    """Download historical ERA5 data for training."""
    parser = argparse.ArgumentParser(description='Download ERA5 atmospheric data.')
    parser.add_argument('--start-year', type=int, default=2023, help='Start year for data download (inclusive)')
    parser.add_argument('--end-year', type=int, default=2023, help='End year for data download (inclusive)')
    parser.add_argument('--wind-only', action='store_true',
                        help='Download only 10 m wind, one request per year (all the training pipeline needs; much faster)')
    
    args = parser.parse_args()
    
    if download_era5_range is None:
        logger.error("Could not import ERA5 download function.")
        sys.exit(1)
        
    logger.info(f"Downloading ERA5 data for {args.start_year}-{args.end_year}...")
    try:
        output_dir = RAW_DIR / "era5"
        if args.wind_only:
            from antarctic_dss.data.era5 import download_era5_wind_year
            for year in range(args.start_year, args.end_year + 1):
                download_era5_wind_year(year, output_dir)
        else:
            download_era5_range(start_year=args.start_year, end_year=args.end_year, output_dir=output_dir)
        logger.info("ERA5 data download complete.")
    except Exception as e:
        logger.error(f"Error downloading ERA5 data: {e}")

if __name__ == '__main__':
    main()
