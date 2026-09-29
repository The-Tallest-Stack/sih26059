import concurrent.futures
from pathlib import Path
from typing import Dict, Tuple

import numpy as np
import pandas as pd
import xarray as xr

from antarctic_dss.data.alignment import build_training_row
from antarctic_dss.models.physics_baseline import batch_free_drift

# Forcing columns the physics baseline needs; missing/NaN values mean "no forcing" (0),
# e.g. no sea-ice drift in open water.
FORCING_COLUMNS = ['wind_u', 'wind_v', 'ocean_current_u', 'ocean_current_v',
                   'seaice_drift_u', 'seaice_drift_v', 'seaice_concentration']

def add_derived_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Add lag features, seasonal cyclic features, and physics baseline predictions.

    Physics predictions are east/north displacements in metres per 24 h, the same frame
    and units as the targets. Lag columns are kept for analysis but are not model features:
    live USNIC positions have no drift history, so they can't be supplied at inference.
    """
    df = df.copy()
    df['timestamp'] = pd.to_datetime(df['timestamp'])

    # Sort by iceberg and time to compute lags
    df = df.sort_values(['iceberg_id', 'timestamp'])

    # Lag features
    df['lag1_dx'] = df.groupby('iceberg_id')['target_dx'].shift(1)
    df['lag1_dy'] = df.groupby('iceberg_id')['target_dy'].shift(1)

    # Seasonal features (month cyclic encoding)
    months = df['timestamp'].dt.month
    df['month_sin'] = np.sin(2 * np.pi * months / 12)
    df['month_cos'] = np.cos(2 * np.pi * months / 12)

    for col in FORCING_COLUMNS:
        if col not in df.columns:
            df[col] = 0.0
        df[col] = df[col].fillna(0.0)
    if 'size_km2' not in df.columns:
        df['size_km2'] = np.nan

    # Physics baseline predictions
    return batch_free_drift(df, dt_seconds=86400.0)

def build_training_table(iceberg_df: pd.DataFrame, env_datasets: Dict[str, xr.Dataset], max_workers: int = 4) -> pd.DataFrame:
    """
    Build complete training DataFrame by sampling env_datasets for each iceberg observation.
    """
    rows = []
    
    # Convert DataFrame to list of dicts for multithreading processing
    records = iceberg_df.to_dict('records')
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [
            executor.submit(build_training_row, record, env_datasets)
            for record in records
        ]
        
        for future in concurrent.futures.as_completed(futures):
            try:
                rows.append(future.result())
            except Exception as e:
                print(f"Error processing row: {e}")
                
    result_df = pd.DataFrame(rows)
    return result_df

def apply_chronological_split(df: pd.DataFrame, train_end: str = '2021-12-31', val_end: str = '2023-12-31') -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """
    Split the dataset chronologically to avoid data leakage.
    NO random shuffling.
    """
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    
    train_mask = df['timestamp'] <= pd.to_datetime(train_end)
    val_mask = (df['timestamp'] > pd.to_datetime(train_end)) & (df['timestamp'] <= pd.to_datetime(val_end))
    test_mask = df['timestamp'] > pd.to_datetime(val_end)
    
    return df[train_mask].copy(), df[val_mask].copy(), df[test_mask].copy()

def save_splits(train: pd.DataFrame, val: pd.DataFrame, test: pd.DataFrame, output_dir: Path):
    """
    Save the dataset splits as Parquet files.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    train.to_parquet(output_dir / 'train.parquet', index=False)
    val.to_parquet(output_dir / 'val.parquet', index=False)
    test.to_parquet(output_dir / 'test.parquet', index=False)
