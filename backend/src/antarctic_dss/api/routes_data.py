from fastapi import APIRouter, HTTPException
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Dict, Any, Optional
import json

import numpy as np

from antarctic_dss.api.schemas import DataFreshnessSchema, VesselProfileSchema
from antarctic_dss.config import FORECAST_ZARR

router = APIRouter()

MODEL_DIR = Path(__file__).parent.parent / "models"
DEFAULT_HORIZONS = [6, 12, 18, 24, 48, 72]
# Coarse grid for map overlays (the forecast is 1/12 degree; 1 degree keeps responses small).
OVERLAY_RESOLUTION_DEG = 1.0

# Endpoints are plain `def` so FastAPI runs the blocking I/O and model work in its threadpool.

def _open_forecast():
    """The cached forecast dataset, or None if data/sync_forecasts.py hasn't been run."""
    if not FORECAST_ZARR.exists():
        return None
    import xarray as xr
    return xr.open_zarr(FORECAST_ZARR)

# Model input name -> forecast cache variable.
FORCING_VARIABLES = {
    'wind_u': 'wind_u', 'wind_v': 'wind_v',
    'ocean_current_u': 'uo', 'ocean_current_v': 'vo',
    'seaice_drift_u': 'usi', 'seaice_drift_v': 'vsi',
    'seaice_concentration': 'siconc',
}
_forcing_cache: Dict[str, Any] = {'mtime': None, 'arrays': None}

def _forcing_arrays(coarsen: int = 3):
    """Forecast forcing as in-memory numpy arrays on a 0.25 degree grid, cached until the
    forecast is re-synced. Point lookups on the lazy Zarr store cost ~50 ms each, which made
    multi-day trajectory prediction for every iceberg take tens of seconds."""
    if not FORECAST_ZARR.exists():
        return None
    import os
    mtime = os.path.getmtime(FORECAST_ZARR)
    if _forcing_cache['mtime'] != mtime:
        ds = _open_forecast()
        variables = [v for v in FORCING_VARIABLES.values() if v in ds]
        coarse = ds[variables].coarsen(latitude=coarsen, longitude=coarsen, boundary='trim').mean().load()
        _forcing_cache['arrays'] = (coarse['time'].values, coarse['latitude'].values, coarse['longitude'].values,
                                    {v: coarse[v].values for v in variables})
        _forcing_cache['mtime'] = mtime
    return _forcing_cache['arrays']

def _parse_time(time: Optional[str]) -> datetime:
    """ISO time string -> naive UTC datetime (defaults to now)."""
    if not time:
        return datetime.now(timezone.utc).replace(tzinfo=None)
    try:
        dt = datetime.fromisoformat(time.replace('Z', '+00:00'))
    except ValueError:
        raise HTTPException(status_code=422, detail=f'Invalid ISO time: {time}')
    return dt.astimezone(timezone.utc).replace(tzinfo=None) if dt.tzinfo else dt

def _cell_polygon(lat: float, lon: float, half: float) -> Dict[str, Any]:
    return {'type': 'Polygon', 'coordinates': [[
        [lon - half, lat - half], [lon + half, lat - half], [lon + half, lat + half],
        [lon - half, lat + half], [lon - half, lat - half]]]}

def _live_icebergs_4326():
    from antarctic_dss.data.usnic_live import fetch_current_icebergs
    gdf = fetch_current_icebergs()
    if 'geom_3031' in gdf.columns:
        gdf = gdf.drop(columns=['geom_3031'])
    return gdf.to_crs(epsg=4326)

@router.get('/icebergs/current')
def get_current_icebergs() -> Dict[str, Any]:
    """Fetch current Antarctic iceberg positions from USNIC (cached ~30 min).

    Returns GeoJSON FeatureCollection with iceberg points and the USNIC table columns
    (Iceberg, Length (NM), Width (NM), Area (sqKM), Last Update, ...).
    """
    try:
        return json.loads(_live_icebergs_4326().to_json())
    except Exception as e:
        raise HTTPException(status_code=503, detail=f'Failed to fetch icebergs: {str(e)}')

def _predict_trajectories(iceberg_id: Optional[str] = None, horizons: Optional[List[int]] = None,
                          start_from_last_update: bool = False, as_objects: bool = False):
    """Run the trajectory model for all live USNIC icebergs, or just one.

    By default trajectories start "now" (the predictor page's +0 h). With
    start_from_last_update, each starts at its USNIC 'Last Update' date, which is when the
    position was actually observed (often days ago), so horizons count from that time.
    Returns GeoJSON, or the IcebergTrajectory objects if as_objects.
    """
    from antarctic_dss.models.xgboost_model import IcebergDisplacementModel
    from antarctic_dss.models.trajectory import TrajectoryGenerator
    from antarctic_dss.models.uncertainty import UncertaintyEstimator
    from antarctic_dss.utils.geo import epsg3031_to_epsg4326

    # 1. Live icebergs
    gdf = _live_icebergs_4326()
    if iceberg_id is not None:
        gdf = gdf[gdf['Iceberg'].astype(str).str.upper() == iceberg_id.upper()]
        if gdf.empty:
            raise HTTPException(status_code=404, detail=f'Iceberg {iceberg_id} not in the current USNIC table')

    # 2. Model (and its calibrated uncertainty growth, if training produced one)
    if not (MODEL_DIR / "model_dx.json").exists():
        raise HTTPException(status_code=500, detail="XGBoost model weights not found. Run scripts/train_pipeline.py first.")
    model = IcebergDisplacementModel()
    model.load(MODEL_DIR)
    uncertainty = UncertaintyEstimator()
    if (MODEL_DIR / "uncertainty.json").exists():
        uncertainty.load(MODEL_DIR / "uncertainty.json")
    generator = TrajectoryGenerator(model=model, uncertainty_estimator=uncertainty)

    # 3. Environmental forecast sampler (in-memory 0.25 degree copy: fast point lookups)
    forcing = _forcing_arrays()

    # Without forecast data, assume no forcing rather than inventing a drift direction.
    no_forcing = {
        'wind_u': 0.0, 'wind_v': 0.0,
        'ocean_current_u': 0.0, 'ocean_current_v': 0.0,
        'seaice_drift_u': 0.0, 'seaice_drift_v': 0.0,
        'seaice_concentration': 0.0
    }

    def env_sampler(x, y, t):
        if forcing is None:
            return no_forcing
        times, lats, lons, arrays = forcing
        lon, lat = epsg3031_to_epsg4326(x, y)
        ti = int(np.abs(times - np.datetime64(t.replace(tzinfo=None))).argmin())
        li = int(np.abs(lats - lat).argmin())
        lj = int(np.abs(lons - (((lon + 180) % 360) - 180)).argmin())
        out = {}
        for key, var in FORCING_VARIABLES.items():
            v = arrays[var][ti, li, lj] if var in arrays else np.nan
            out[key] = 0.0 if np.isnan(v) else float(v)
        return out

    # 4. Predict
    now = datetime.now(timezone.utc)
    trajectories = []
    for idx, row in gdf.iterrows():
        # Same size definition as training (BYU size_1 x size_2, nautical miles -> km^2).
        try:
            size_km2 = float(row['Length (NM)']) * float(row['Width (NM)']) * 1.852 ** 2
        except (KeyError, TypeError, ValueError):
            size_km2 = np.nan
        start = now
        if start_from_last_update:
            observed = latest_usnic_update(pd_series([row.get('Last Update')]))
            start = min(observed, now) if observed is not None else now
        month = start.month
        state = {
            'iceberg_id': row.get('Iceberg', f'Iceberg-{idx}'),
            'time': start,
            'lat': row.geometry.y,
            'lon': row.geometry.x,
            'size_km2': size_km2,
            'month_sin': np.sin(2 * np.pi * month / 12),
            'month_cos': np.cos(2 * np.pi * month / 12)
        }
        trajectories.append(generator.predict_trajectory(state, env_sampler, horizons_hours=horizons or DEFAULT_HORIZONS))

    return trajectories if as_objects else generator.all_to_geojson(trajectories)

@router.get('/icebergs/predict_all')
def predict_all_icebergs() -> Dict[str, Any]:
    """Predict trajectories for all current USNIC icebergs."""
    try:
        return _predict_trajectories()
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get('/icebergs/{iceberg_id}/trajectory')
def get_iceberg_trajectory(iceberg_id: str, horizon_hours: int = 72) -> Dict[str, Any]:
    """Predicted trajectory (GeoJSON Feature) for one USNIC iceberg, up to horizon_hours ahead."""
    if not 1 <= horizon_hours <= 240:
        raise HTTPException(status_code=422, detail='horizon_hours must be between 1 and 240')
    horizons = [h for h in DEFAULT_HORIZONS if h < horizon_hours] + [horizon_hours]
    try:
        return _predict_trajectories(iceberg_id, horizons)['features'][0]
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get('/environment/seaice')
def get_sea_ice_data(time: Optional[str] = None) -> Dict[str, Any]:
    """Sea-ice concentration from the cached Copernicus forecast, on a 1 degree grid.

    Returns GeoJSON polygons for cells with >= 15% ice (the conventional ice edge),
    with properties `siconc` (0-1) and the forecast `time` used.
    """
    ds = _open_forecast()
    if ds is None or 'siconc' not in ds:
        raise HTTPException(status_code=503, detail='No sea-ice forecast cached. Run data/sync_forecasts.py.')

    t = _parse_time(time)
    slice_ds = ds['siconc'].sel(time=np.datetime64(t), method='nearest')
    step = abs(float(ds['latitude'][1] - ds['latitude'][0]))
    factor = max(1, int(round(OVERLAY_RESOLUTION_DEG / step)))
    coarse = slice_ds.coarsen(latitude=factor, longitude=factor, boundary='trim').mean().load()

    half = factor * step / 2
    features = []
    values = coarse.values
    lats, lons = coarse['latitude'].values, coarse['longitude'].values
    for i, j in zip(*np.nonzero(np.nan_to_num(values) >= 0.15)):
        features.append({
            'type': 'Feature',
            'geometry': _cell_polygon(float(lats[i]), float(lons[j]), half),
            'properties': {'siconc': round(float(values[i, j]), 3)},
        })
    return {'type': 'FeatureCollection', 'features': features,
            'properties': {'time': str(slice_ds['time'].values)[:19], 'resolution_deg': factor * step}}

@router.get('/environment/risk-map')
def get_risk_map(time: Optional[str] = None, vessel_id: str = 'icebreaker_pc5') -> Dict[str, Any]:
    """Time-sliced navigation risk map for a vessel, on a 1 degree grid.

    Uses the same cost model as the router (sea ice, iceberg proximity, wind, waves).
    Properties: `risk` in [0, 1] (1 = impassable for this vessel) and `impassable`.
    Land cells are omitted. If no time is specified, returns current conditions.
    """
    from antarctic_dss.routing.risk_map import TimeDependentRiskMap, RiskMapConfig
    from antarctic_dss.routing.vessel import DEFAULT_VESSELS
    from antarctic_dss.api.routes_voyage import _build_land_mask

    vessel = DEFAULT_VESSELS.get(vessel_id)
    if vessel is None:
        raise HTTPException(status_code=404, detail=f'Unknown vessel_id {vessel_id}')
    t = _parse_time(time)

    try:
        icebergs = [(g.y, g.x) for g in _live_icebergs_4326().geometry]
    except Exception:
        icebergs = []

    config = RiskMapConfig(lat_min=-80.0, lat_max=-55.0, lon_min=-180.0, lon_max=180.0,
                           resolution_deg=OVERLAY_RESOLUTION_DEG, time_step_hours=6)
    risk_map = TimeDependentRiskMap(config=config)
    env_data: Dict[str, Any] = {'sic': 0.1, 'wind_speed': 5.0, 'depth_m': 1000.0}
    ds = _open_forecast()
    if ds is not None:
        env_data['dataset'] = ds
    from antarctic_dss.routing.bathymetry import depth_on_grid
    depth = depth_on_grid(risk_map.lat_grid, risk_map.lon_grid, OVERLAY_RESOLUTION_DEG)
    if depth is not None:
        env_data['real_depth_m'] = depth
    risk_map.build_all_slices(start_time=t, duration_hours=0, env_data=env_data,
                              iceberg_trajectories=icebergs, vessel=vessel)
    cost = risk_map.cost_grids[t]
    land = _build_land_mask(risk_map)

    # Map unbounded cell cost to [0, 1): ~0.4 at 50% ice, ~1 near icebergs.
    risk = np.where(np.isinf(cost), 1.0, 1.0 - np.exp(-np.nan_to_num(cost, posinf=0.0) / 200.0))
    half = OVERLAY_RESOLUTION_DEG / 2
    features = []
    for i, j in zip(*np.nonzero((risk > 0.01) & ~land)):
        lat, lon = risk_map.idx_to_coord(i, j)
        features.append({
            'type': 'Feature',
            'geometry': _cell_polygon(lat, lon, half),
            'properties': {'risk': round(float(risk[i, j]), 3), 'impassable': bool(np.isinf(cost[i, j]))},
        })
    return {'type': 'FeatureCollection', 'features': features,
            'properties': {'time': t.isoformat(), 'vessel_id': vessel_id,
                           'real_data': bool(risk_map.env_slices[t].from_real_data)}}

def _age_minutes(now: datetime, then: Optional[datetime]) -> float:
    return max(0.0, (now - then).total_seconds() / 60.0) if then else 0.0

@router.get('/data/freshness', response_model=List[DataFreshnessSchema])
def get_data_freshness() -> List[DataFreshnessSchema]:
    """Get data source freshness status.

    Status is 'fresh', 'stale', 'unavailable', or 'synthetic' (placeholder data, not a
    real feed). `last_updated` is when the source data was produced/synced, not "now".
    """
    now = datetime.now(timezone.utc)
    sources = []

    # USNIC: age of the newest analysis in the table (USNIC updates roughly weekly).
    from antarctic_dss.data.usnic_live import fetch_current_icebergs, fetch_status
    try:
        gdf = fetch_current_icebergs()
        analysed = latest_usnic_update(gdf['Last Update']) if 'Last Update' in gdf else None
        last = analysed or fetch_status()['fetched_at']
        age = _age_minutes(now, last)
        stale = age > 8 * 24 * 60 or fetch_status()['last_error'] is not None
        sources.append(DataFreshnessSchema(source='USNIC Icebergs', last_updated=last, age_minutes=age,
                                           status='stale' if stale else 'fresh'))
    except Exception:
        sources.append(DataFreshnessSchema(source='USNIC Icebergs', last_updated=None, age_minutes=0, status='unavailable'))

    # Forecast cache: sync time, and whether "now" is still inside the forecast's coverage.
    ds = _open_forecast()
    if ds is None:
        for name in ('Copernicus Sea Ice Forecast', 'Copernicus Ocean Currents', 'Wind Forecast'):
            sources.append(DataFreshnessSchema(source=name, last_updated=None, age_minutes=0, status='unavailable'))
        return sources

    synced_at = ds.attrs.get('synced_at')
    if synced_at:
        synced = datetime.fromisoformat(synced_at)
    else:
        import os
        synced = datetime.fromtimestamp(os.path.getmtime(FORECAST_ZARR), tz=timezone.utc)
    age = _age_minutes(now, synced)
    coverage_end = datetime.fromisoformat(str(ds['time'].values.max())[:19]).replace(tzinfo=timezone.utc) + timedelta(days=1)
    cache_status = 'fresh' if age < 24 * 60 and now <= coverage_end else 'stale'

    def forecast_source(name: str, available: bool, status: str = cache_status):
        return DataFreshnessSchema(source=name, last_updated=synced if available else None,
                                   age_minutes=age if available else 0,
                                   status=status if available else 'unavailable')

    sources.append(forecast_source('Copernicus Sea Ice Forecast', 'siconc' in ds))
    sources.append(forecast_source('Copernicus Ocean Currents', 'uo' in ds and 'vo' in ds))
    # The sync script fills wind with random placeholder values (older caches lack the flag).
    wind_synthetic = bool(ds.attrs.get('wind_is_synthetic', 1))
    sources.append(forecast_source('Wind Forecast', 'wind_u' in ds,
                                   status='synthetic' if wind_synthetic else cache_status))
    return sources

def pd_series(values):
    import pandas as pd
    return pd.Series(values)

def drift_model_beats_persistence() -> bool:
    """True if the trained model beat the no-motion baseline on its held-out test period."""
    path = MODEL_DIR / 'training_metrics.json'
    if not path.exists() or not (MODEL_DIR / 'model_dx.json').exists():
        return False
    try:
        with open(path) as f:
            m = json.load(f)
        return m['test_model']['mean_position_error_km'] < m['test_no_motion_baseline']['mean_position_error_km']
    except (KeyError, ValueError, OSError):
        return False

def latest_usnic_update(series) -> Optional[datetime]:
    """Newest 'Last Update' date (MM/DD/YYYY) in the USNIC table, as UTC."""
    import pandas as pd
    parsed = pd.to_datetime(series, format='%m/%d/%Y', errors='coerce', utc=True)
    return parsed.max().to_pydatetime() if parsed.notna().any() else None

@router.get('/vessels', response_model=List[VesselProfileSchema])
def list_vessels() -> List[VesselProfileSchema]:
    """List available vessel profiles."""
    from antarctic_dss.routing.vessel import DEFAULT_VESSELS
    return [
        VesselProfileSchema(
            id=vid, name=v.name, max_speed_knots=v.max_speed_knots,
            max_ice_concentration=v.max_ice_concentration,
            ice_speed_factor=v.ice_speed_factor, draft_m=v.draft_m,
            ice_class=v.ice_class, description=v.description,
            max_ice_thickness_m=v.max_ice_thickness_m if np.isfinite(v.max_ice_thickness_m) else None,
        )
        for vid, v in DEFAULT_VESSELS.items()
    ]
