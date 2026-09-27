import argparse
import sys
import logging
from pathlib import Path

# Add backend/src to path
sys.path.append(str(Path(__file__).resolve().parent.parent / "backend" / "src"))

try:
    from antarctic_dss.data.nsidc import download_g02202
    from antarctic_dss.config import RAW_DIR
except ImportError as e:
    print(f"ImportError: {e}")
    download_g02202 = None

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def main():
    """Download NSIDC G02202 southern hemisphere sea ice concentration data."""
    parser = argparse.ArgumentParser(description='Download NSIDC G02202 sea ice concentration data.')
    parser.add_argument('--start-date', type=str, default='2023-01-01', help='Start date (YYYY-MM-DD)')
    parser.add_argument('--end-date', type=str, default='2023-01-31', help='End date (YYYY-MM-DD)')
    
    args = parser.parse_args()
    
    if download_g02202 is None:
        logger.error("Could not import NSIDC download function.")
        sys.exit(1)
        
    logger.info(f"Downloading NSIDC data from {args.start_date} to {args.end_date}...")
    try:
        output_dir = RAW_DIR / "nsidc"
        download_g02202(start_date=args.start_date, end_date=args.end_date, output_dir=output_dir)
        logger.info("NSIDC data download complete.")
    except Exception as e:
        logger.error(f"Error downloading NSIDC data: {e}")

if __name__ == '__main__':
    main()
