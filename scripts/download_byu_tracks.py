import os
import ssl
import urllib.request
import zipfile
from pathlib import Path

def download_and_extract(url: str, extract_dir: Path):
    """
    Downloads a zip file from a URL and extracts it to a directory.
    
    Args:
        url (str): The URL of the zip file to download.
        extract_dir (Path): The directory to extract the contents to.
    """
    extract_dir.mkdir(parents=True, exist_ok=True)
    zip_path = extract_dir / "temp.zip"
    
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    
    print(f"Downloading {url}...")
    try:
        with urllib.request.urlopen(req, context=ctx) as response, open(zip_path, 'wb') as out_file:
            data = response.read()
            out_file.write(data)
            
        print(f"Extracting to {extract_dir}...")
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(extract_dir)
    finally:
        if zip_path.exists():
            zip_path.unlink()
            
if __name__ == '__main__':
    base_dir = Path(r"c:\Users\karthi\sih26059")
    
    consolidated_url = "https://www.scp.byu.edu/data/iceberg/consolidated_database_v8.0.zip"
    consolidated_dir = base_dir / "data" / "raw" / "iceberg_tracks" / "consolidated_v8"
    download_and_extract(consolidated_url, consolidated_dir)
    
    stats_url = "https://www.scp.byu.edu/data/iceberg/stats_database_v7.1.zip"
    stats_dir = base_dir / "data" / "raw" / "iceberg_tracks" / "stats_v7"
    download_and_extract(stats_url, stats_dir)
