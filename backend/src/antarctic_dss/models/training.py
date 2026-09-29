"""End-to-end training of the iceberg displacement model.

Pipeline: BYU/NIC consolidated tracks -> daily east/north displacement targets ->
forcing sampled from ERA5 / Copernicus reanalysis over each 24 h window -> derived
features -> chronological train/val/test split -> XGBoost with early stopping ->
evaluation against the physics baseline on the held-out test period.
"""
import glob
import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import xarray as xr

from antarctic_dss.data.alignment import sample_environment
from antarctic_dss.data.iceberg_tracks import load_consolidated_training_tracks
from antarctic_dss.data.training_table import add_derived_features, apply_chronological_split
from antarctic_dss.models.physics_baseline import evaluate_physics_baseline
from antarctic_dss.models.uncertainty import UncertaintyEstimator
from antarctic_dss.models.xgboost_model import IcebergDisplacementModel

CONSOLIDATED_SUBDIR = Path('iceberg_tracks') / 'consolidated_v8' / 'updated7_consol'

# Variables used per source. Files from different downloads differ (extra ERA5 variables,
# 9 depth levels vs surface-only ocean files), so each file is reduced to these, at the
# surface, before combining.
SOURCE_VARIABLES = {
    'era5': ['u10', 'v10'],
    'ocean': ['uo', 'vo'],
    'seaice_drift': ['eastward_sea_ice_velocity', 'northward_sea_ice_velocity'],
    'seaice_model': ['siconc', 'usi', 'vsi'],
}

def _preprocess(key: str):
    def reduce(ds: xr.Dataset) -> xr.Dataset:
        ds = ds[[v for v in SOURCE_VARIABLES[key] if v in ds.data_vars]]
        if 'depth' in ds.dims:
            ds = ds.isel(depth=0, drop=True)
        return ds.drop_vars([c for c in ds.coords if c not in ds.dims])
    return reduce

def era5_daily_cache(raw_dir: Path) -> str:
    """Daily-mean 10 m wind, one file per ERA5 download, built once; returns a glob pattern.

    The CDS NetCDF files store data in large compressed blocks, so reading one day at a time
    from them decompresses a big part of the file every time (~10 s/day for yearly files).
    Averaging the four 6-hourly steps per day once, stored one day per chunk, makes alignment
    reads cheap; window means over whole days are unchanged.
    """
    cache_dir = raw_dir.parent / 'processed' / 'era5_daily'
    cache_dir.mkdir(parents=True, exist_ok=True)
    for src in sorted(glob.glob(str(raw_dir / 'era5' / '*_unzipped' / 'data_stream-oper_stepType-instant.nc'))):
        out = cache_dir / f"{Path(src).parent.name.replace('_unzipped', '')}_daily.nc"
        if out.exists():
            continue
        print(f"  era5: building daily-mean cache {out.name}...", flush=True)
        with xr.open_dataset(src) as ds:
            daily = xr.Dataset({
                var: ds[var].resample(valid_time='1D').mean().astype('float32').load()
                for var in SOURCE_VARIABLES['era5'] if var in ds.data_vars
            })
        encoding = {v: {'zlib': True, 'complevel': 1,
                        'chunksizes': (1, daily.sizes['latitude'], daily.sizes['longitude'])} for v in daily.data_vars}
        tmp = out.with_suffix('.tmp')
        daily.to_netcdf(tmp, encoding=encoding)
        tmp.rename(out)
    return str(cache_dir / '*_daily.nc')

def open_env_datasets(raw_dir: Path) -> Dict[str, xr.Dataset]:
    """Lazily open whichever downloaded environmental datasets are present."""
    sources = {
        'era5': era5_daily_cache(raw_dir),
        'ocean': str(raw_dir / 'copernicus' / 'ocean_reanalysis' / '*.nc'),
        'seaice_drift': str(raw_dir / 'copernicus' / 'seaice_drift_reprocessed' / '*.nc'),
        'seaice_model': str(raw_dir / 'copernicus' / 'seaice_reanalysis' / '*.nc'),
    }
    datasets = {}
    for key, pattern in sources.items():
        files = sorted(glob.glob(pattern))
        if not files:
            print(f"  {key}: no files found ({pattern})")
            continue
        try:
            # One time step per chunk: the aligner reads one day at a time, and the default
            # (one chunk per file) would load a whole ~1.7 GB month for every day sampled.
            time_dim = 'valid_time' if key == 'era5' else 'time'
            datasets[key] = xr.open_mfdataset(files, combine='by_coords', chunks={time_dim: 1},
                                              preprocess=_preprocess(key))
            print(f"  {key}: {len(files)} files")
        except Exception as e:
            print(f"  {key}: failed to open ({e})")
    if 'seaice_model' in datasets and 'seaice_drift' in datasets:
        # Prefer the reanalysis ice velocity: it's what the live forecast provides at inference.
        print("  seaice_drift: skipped (using seaice_model usi/vsi instead)")
        del datasets['seaice_drift']
    return datasets

def build_training_table(raw_dir: Path, years: List[int]) -> pd.DataFrame:
    """Clean iceberg displacement targets for `years`, aligned with environmental forcing."""
    tracks = load_consolidated_training_tracks(raw_dir / CONSOLIDATED_SUBDIR, years=years)
    if tracks.empty:
        return tracks
    print(f"Loaded {len(tracks)} daily displacements from {tracks['iceberg_id'].nunique()} icebergs in {years}.")
    env = open_env_datasets(raw_dir)
    return sample_environment(tracks, env)

SEASONS = {12: 'DJF', 1: 'DJF', 2: 'DJF', 3: 'MAM', 4: 'MAM', 5: 'MAM',
           6: 'JJA', 7: 'JJA', 8: 'JJA', 9: 'SON', 10: 'SON', 11: 'SON'}

def chronological_split_dates(years: List[int]) -> Tuple[str, str]:
    """(train_end, val_end): by year with 3+ years (test = last year, val = the one before),
    otherwise within the last year (train to July, validate Aug-Sep, test Oct-Dec)."""
    years = sorted(years)
    if len(years) >= 3:
        return f"{years[-3]}-12-31", f"{years[-2]}-12-31"
    return f"{years[-1]}-07-31", f"{years[-1]}-09-30"

def _position_error_km(df: pd.DataFrame, dx: np.ndarray, dy: np.ndarray) -> float:
    return float(np.mean(np.hypot(dx - df['target_dx'].values, dy - df['target_dy'].values)) / 1000.0)

def season_breakdown(model: IcebergDisplacementModel, test: pd.DataFrame) -> Dict[str, Dict]:
    """Mean 24 h position error (km) per season for the model and the baselines."""
    out = {}
    seasons = test['timestamp'].dt.month.map(SEASONS)
    for season in ['DJF', 'MAM', 'JJA', 'SON']:
        part = test[seasons == season]
        if len(part) < 10:
            continue
        dx, dy = model.predict(part)
        out[season] = {
            'rows': len(part),
            'xgboost_km': _position_error_km(part, dx, dy),
            'physics_km': _position_error_km(part, part['physics_pred_dx'].values, part['physics_pred_dy'].values),
            'no_motion_km': _position_error_km(part, np.zeros(len(part)), np.zeros(len(part))),
        }
    return out

def train_and_evaluate(table: pd.DataFrame, model_dir: Path, train_end: str, val_end: str) -> Optional[Dict]:
    """Train on the chronological split, report test metrics vs physics, and save artifacts."""
    df = add_derived_features(table.dropna(subset=['target_dx', 'target_dy']))
    if 'grounded' not in df.columns:
        df['grounded'] = False
    df['grounded'] = df['grounded'].fillna(False).astype(bool)
    train, val, test_all = apply_chronological_split(df, train_end=train_end, val_end=val_end)
    # Grounded icebergs don't respond to forcing: train and headline-evaluate on free drift only.
    n_grounded = int(train['grounded'].sum() + val['grounded'].sum())
    train, val = train[~train['grounded']], val[~val['grounded']]
    test = test_all[~test_all['grounded']]
    print(f"Split: train={len(train)} (<= {train_end}), val={len(val)} (<= {val_end}), "
          f"test={len(test)} free-drifting / {len(test_all)} total; {n_grounded} grounded rows excluded from train/val")
    if len(train) < 50 or len(val) < 10 or len(test) < 10:
        print("Not enough data in one of the splits to train and evaluate.")
        return None

    model = IcebergDisplacementModel()
    model.train(train, val)

    test_model = model.evaluate(test)
    test_physics = {k: float(v) for k, v in evaluate_physics_baseline(test).items()}
    # "Persistence" baseline: predict no motion. Any useful model must beat this.
    zero = test.assign(physics_pred_dx=0.0, physics_pred_dy=0.0)
    test_zero = {k: float(v) for k, v in evaluate_physics_baseline(zero).items()}

    # Uncertainty radius: 68th-percentile 24 h validation error, growing linearly with horizon.
    val_dx, val_dy = model.predict(val)
    val_err_km = np.hypot(val_dx - val['target_dx'], val_dy - val['target_dy']) / 1000.0
    uncertainty = UncertaintyEstimator()
    uncertainty.a = float(np.percentile(val_err_km, 68)) / 24.0
    uncertainty.b = 0.0

    model.save(model_dir)
    uncertainty.save(model_dir / 'uncertainty.json')

    metrics = {
        'rows': {'train': len(train), 'val': len(val), 'test': len(test)},
        'split': {'train_end': train_end, 'val_end': val_end},
        'best_iteration': {'dx': int(model.model_dx.best_iteration), 'dy': int(model.model_dy.best_iteration)},
        'test_model': test_model,
        'test_physics_baseline': test_physics,
        'test_no_motion_baseline': test_zero,
        'test_by_season': season_breakdown(model, test),
        'test_including_grounded': {
            'rows': len(test_all),
            'xgboost_km': _position_error_km(test_all, *model.predict(test_all)),
            'no_motion_km': _position_error_km(test_all, np.zeros(len(test_all)), np.zeros(len(test_all))),
        },
        'uncertainty_km_per_hour': uncertainty.a,
        'feature_importance': model.feature_importance()[['feature', 'importance_mean']].to_dict('records'),
    }
    with open(model_dir / 'training_metrics.json', 'w') as f:
        json.dump(metrics, f, indent=2, default=float)

    print("\nTest-period mean position error after 24 h (km):")
    print(f"  XGBoost:           {test_model['mean_position_error_km']:.2f}")
    print(f"  Physics baseline:  {test_physics['mean_position_error_km']:.2f}")
    print(f"  No-motion:         {test_zero['mean_position_error_km']:.2f}")
    inc = metrics['test_including_grounded']
    print(f"  (incl. grounded, {inc['rows']} rows: XGBoost {inc['xgboost_km']:.2f}, no-motion {inc['no_motion_km']:.2f})")
    return metrics
