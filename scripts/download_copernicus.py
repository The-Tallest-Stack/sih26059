import argparse
import sys
import logging
from pathlib import Path

# Add backend/src to path
sys.path.append(str(Path(__file__).resolve().parent.parent / "backend" / "src"))

try:
    from antarctic_dss.data.copernicus import download_historical_range
    from antarctic_dss.config import RAW_DIR
except ImportError as e:
    print(f"ImportError: {e}")
    download_historical_range = None

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def main():
    """Download historical Copernicus data for training."""
    parser = argparse.ArgumentParser(description='Download Copernicus Data (Sea Ice Drift, Ocean Reanalysis).')
    parser.add_argument('--start-year', type=int, default=2023, help='Start year for data download (inclusive)')
    parser.add_argument('--end-year', type=int, default=2023, help='End year for data download (inclusive)')
    parser.add_argument('--dataset', type=str, choices=['seaice_drift_reprocessed', 'ocean_reanalysis', 'all'], default='all', help='Dataset to download')
    
    args = parser.parse_args()
    
    if download_historical_range is None:
        logger.error("Could not import Copernicus download functions.")
        sys.exit(1)
        
    datasets = ['seaice_drift_reprocessed', 'ocean_reanalysis'] if args.dataset == 'all' else [args.dataset]
    
    for ds_name in datasets:
        logger.info(f"Downloading {ds_name} for {args.start_year}-{args.end_year}...")
        try:
            output_dir = RAW_DIR / "copernicus" / ds_name
            download_historical_range(
                config_name=ds_name, 
                start_year=args.start_year, 
                end_year=args.end_year,
                output_dir=output_dir
            )
            logger.info(f"{ds_name} download complete.")
        except Exception as e:
            logger.error(f"Error downloading {ds_name}: {e}")

if __name__ == '__main__':
    main()
