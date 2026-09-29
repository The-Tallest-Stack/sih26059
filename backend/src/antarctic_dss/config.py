"""Configuration module for the Antarctic Voyage Decision Support System."""

import os
from pathlib import Path
from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

# Load .env from project root
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
ENV_FILE = PROJECT_ROOT / ".env"
load_dotenv(ENV_FILE)

class Settings(BaseSettings):
    """Application settings and credentials."""

    COPERNICUS_USERNAME: str = ""
    COPERNICUS_PASSWORD: str = ""
    CDS_API_KEY: str = ""
    EARTHDATA_USERNAME: str = ""
    EARTHDATA_PASSWORD: str = ""

    # Directory
    DATA_DIR: Path = PROJECT_ROOT / "data"

    model_config = SettingsConfigDict(
        env_file=str(ENV_FILE), 
        env_file_encoding="utf-8", 
        extra="ignore"
    )

settings = Settings()

# Setup paths
DATA_DIR = settings.DATA_DIR
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"
MODELS_DIR = DATA_DIR / "models"
CACHE_DIR = DATA_DIR / "cache"

# Backend-local cache of the environmental forecast (written by data/sync_forecasts.py,
# read by the API). Kept separate from the training data under DATA_DIR.
BACKEND_DIR = PROJECT_ROOT / "backend"
FORECAST_ZARR = BACKEND_DIR / "data" / "cache" / "forecast.zarr"
