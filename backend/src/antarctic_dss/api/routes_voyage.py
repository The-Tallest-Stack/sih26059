from fastapi import APIRouter, HTTPException
from datetime import datetime, timedelta, timezone
from pathlib import Path
import json
import math
import os
import uuid
from typing import Dict, Any, List, Tuple

import numpy as np

from antarctic_dss.api.schemas import VoyageRequest, VoyageResultSchema

router = APIRouter()

# In-memory store for demo (would be database in production)
_voyage_results: Dict[str, Any] = {}

# Bound the number of A* runs per request; the interval is widened for long windows.
MAX_CANDIDATE_DEPARTURES = 16
# All candidates are evaluated; only the lowest-risk few are returned to the UI.
MAX_OPTIONS_RETURNED = 3
ICEBERG_PROXIMITY_KM = 60.0
from antarctic_dss.config import FORECAST_ZARR
DATA_DIR = os.path.join(os.path.dirname(__file__), '..', 'data')

_land_mask_cache: Dict[Tuple, np.ndarray] = {}
_blocked_edges_cache: Dict[Tuple, Dict] = {}
_land_gdf = None

def _land_geometries():
    """Land + ice shelf polygons (EPSG:4326), loaded once."""
    global _land_gdf
    if _land_gdf is None:
        import geopandas as gpd
        import pandas as pd
        land_gdf = gpd.read_file(os.path.join(DATA_DIR, 'land_mask.geojson'))
        try:
            shelves_gdf = gpd.read_file(os.path.join(DATA_DIR, 'ice_shelves.geojson'))
            _land_gdf = gpd.GeoDataFrame(pd.concat([land_gdf, shelves_gdf], ignore_index=True), crs=land_gdf.crs)
        except Exception:
            _land_gdf = land_gdf
    return _land_gdf

def _grid_key(risk_map) -> Tuple:
    return (risk_map.n_lat, risk_map.n_lon, float(risk_map.lat_grid[0]), float(risk_map.lon_grid[0]),
            risk_map.config.resolution_deg)

def _build_blocked_edges(risk_map) -> Dict[Tuple[int, int], np.ndarray]:
    """For each step direction, which cell-to-cell segments cross land (cached per grid).

    Catches islands smaller than a grid cell, which the cell-centre land mask misses.
    """
    key = _grid_key(risk_map)
    if key in _blocked_edges_cache:
        return _blocked_edges_cache[key]

    from shapely import linestrings
    from antarctic_dss.routing.astar import EDGE_DIRECTIONS

    land = _land_geometries()
    lat, lon = np.meshgrid(risk_map.lat_grid, risk_map.lon_grid, indexing='ij')
    res = risk_map.config.resolution_deg
    edges = {}
    for dlat, dlon in EDGE_DIRECTIONS:
        lat2 = lat + dlat * res
        lon2 = lon + dlon * res  # unwrapped (may exceed 180): keeps antimeridian steps short
        valid = (lat2 <= risk_map.lat_grid[-1] + 1e-9) & (lat2 >= risk_map.lat_grid[0] - 1e-9)
        if not risk_map.wrap_lon:
            valid &= (lon2 <= risk_map.lon_grid[-1] + 1e-9) & (lon2 >= risk_map.lon_grid[0] - 1e-9)
        coords = np.stack([np.stack([lon[valid], lat[valid]], -1), np.stack([lon2[valid], lat2[valid]], -1)], 1)
        lines = linestrings(coords)
        hit_lines, _ = land.sindex.query(lines, predicate='intersects')
        # Steps past +/-180 also need checking against the wrapped longitude.
        over = np.nonzero(np.abs(coords[:, 1, 0]) > 180)[0]
        if len(over):
            wrapped = coords[over].copy()
            wrapped[:, :, 0] -= 360.0 * np.sign(wrapped[:, 1:2, 0])
            hit_wrapped, _ = land.sindex.query(linestrings(wrapped), predicate='intersects')
            hit_lines = np.concatenate([hit_lines, over[hit_wrapped]])
        flat = np.zeros(int(valid.sum()), dtype=bool)
        flat[np.unique(hit_lines)] = True
        blocked = np.zeros(lat.shape, dtype=bool)
        blocked[valid] = flat
        edges[(dlat, dlon)] = blocked
    _blocked_edges_cache[key] = edges
    return edges

def _to_utc_naive(dt: datetime) -> datetime:
    """All internal times are naive UTC (forecast datasets use naive UTC timestamps)."""
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt

def _build_land_mask(risk_map) -> np.ndarray:
    """Rasterise land + ice shelves onto the risk-map grid (cached per grid geometry)."""
    key = _grid_key(risk_map)
    if key in _land_mask_cache:
        return _land_mask_cache[key]

    import geopandas as gpd
    combined_gdf = _land_geometries()

    lat, lon = np.meshgrid(risk_map.lat_grid, risk_map.lon_grid, indexing='ij')
    points_gdf = gpd.GeoDataFrame(geometry=gpd.points_from_xy(lon.ravel(), lat.ravel()), crs="EPSG:4326")
    intersected = gpd.sjoin(points_gdf, combined_gdf, how="inner", predicate="intersects")

    flat = np.zeros(lat.size, dtype=bool)
    flat[np.unique(intersected.index.values)] = True
    land_mask = flat.reshape(lat.shape)
    _land_mask_cache[key] = land_mask
    return land_mask

def _icebergs_near(points: List[Tuple[float, float]], icebergs: List[Tuple[float, float]]) -> set:
    """Indices of icebergs within ICEBERG_PROXIMITY_KM of any of the given points."""
    if not points or not icebergs:
        return set()
    from antarctic_dss.utils.geo import haversine_km_array
    pts = np.asarray(points)
    ice = np.asarray(icebergs)
    dists = haversine_km_array(pts[:, None, 0], pts[:, None, 1], ice[None, :, 0], ice[None, :, 1])
    return set(np.nonzero((dists < ICEBERG_PROXIMITY_KM).any(axis=0))[0].tolist())

def _densify(path: List[Tuple[float, float]], spacing_km: float = 10.0) -> List[Tuple[float, float]]:
    from antarctic_dss.utils.geo import great_circle_points
    if len(path) < 2:
        return list(path)
    out = []
    for a, b in zip(path[:-1], path[1:]):
        out.extend(great_circle_points(a[0], a[1], b[0], b[1], spacing_km)[:-1])
    out.append(path[-1])
    return out

def _line_feature(path: List[Tuple[float, float]], properties: Dict[str, Any]) -> Dict[str, Any]:
    from antarctic_dss.utils.geo import unwrap_lons
    lons = unwrap_lons([p[1] for p in path])
    return {
        'type': 'Feature',
        'geometry': {'type': 'LineString', 'coordinates': [[lon, p[0]] for lon, p in zip(lons, path)]},
        'properties': properties,
    }

PREDICTION_STEP_HOURS = 12

def _predicted_positions(window_start: datetime, duration_hours: int):
    """Callable time -> [(lat, lon, uncertainty_km)] from the drift model, or None if the model
    hasn't beaten the no-motion baseline. Trajectories start at each iceberg's USNIC observation
    date; positions are linearly interpolated between horizons and held after the last one."""
    from antarctic_dss.api.routes_data import _predict_trajectories, drift_model_beats_persistence
    if not drift_model_beats_persistence():
        return None

    # USNIC positions are typically a few days old: predict from the observation up to the end
    # of the planning horizon.
    end = window_start.replace(tzinfo=timezone.utc) + timedelta(hours=duration_hours)
    from antarctic_dss.api.routes_data import _live_icebergs_4326
    import pandas as pd
    observed = pd.to_datetime(_live_icebergs_4326()['Last Update'], format='%m/%d/%Y', errors='coerce', utc=True)
    oldest = observed.min().to_pydatetime() if observed.notna().any() else datetime.now(timezone.utc)
    span_h = max(PREDICTION_STEP_HOURS, int(math.ceil((end - oldest).total_seconds() / 3600)))
    horizons = list(range(PREDICTION_STEP_HOURS, span_h + PREDICTION_STEP_HOURS, PREDICTION_STEP_HOURS))
    trajectories = _predict_trajectories(horizons=horizons, start_from_last_update=True, as_objects=True)

    tracks = []
    for traj in trajectories:
        times = [traj.start_time.timestamp()] + [p.time.timestamp() for p in traj.points]
        lats = [traj.start_lat] + [p.lat for p in traj.points]
        lons = [traj.start_lon] + [p.lon for p in traj.points]
        unc = [0.0] + [p.uncertainty_radius_km for p in traj.points]
        from antarctic_dss.utils.geo import unwrap_lons
        tracks.append((np.array(times), np.array(lats), np.array(unwrap_lons(lons)), np.array(unc)))

    def positions_at(t: datetime):
        ts = t.replace(tzinfo=timezone.utc).timestamp()
        out = []
        for times, lats, lons, unc in tracks:
            lon = float(np.interp(ts, times, lons))
            out.append((float(np.interp(ts, times, lats)), ((lon + 180) % 360) - 180, float(np.interp(ts, times, unc))))
        return out
    return positions_at

@router.post('/plan', response_model=VoyageResultSchema)
def plan_voyage(request: VoyageRequest) -> VoyageResultSchema:
    """Submit a voyage planning request.

    Evaluates multiple candidate departure times within the specified window
    and returns compared route options with risk assessments, lowest risk first.

    This is the core endpoint of the system. It:
    1. Loads current environmental data and iceberg positions
    2. Builds time-dependent risk maps covering the window plus the voyage duration
    3. Runs risk-weighted, vessel-specific A* routing for each candidate departure
    4. Compares departure options

    Declared as a plain `def` so FastAPI runs this CPU-heavy work in its threadpool
    instead of blocking the event loop.
    """
    window_start = _to_utc_naive(request.window_start)
    window_end = _to_utc_naive(request.window_end)
    if window_end < window_start:
        raise HTTPException(status_code=422, detail='window_end must be after window_start')

    try:
        voyage_id = str(uuid.uuid4())

        from antarctic_dss.routing.departure import evaluate_departure_window
        from antarctic_dss.routing.vessel import DEFAULT_VESSELS
        from antarctic_dss.routing.risk_map import TimeDependentRiskMap, RiskMapConfig
        from antarctic_dss.routing.astar import RoutingGrid
        from antarctic_dss.utils.geo import haversine_distance, great_circle_points

        # 1. Vessel
        vessel = DEFAULT_VESSELS.get(request.vessel_id, list(DEFAULT_VESSELS.values())[0])
        start_coord = (request.point_a.lat, request.point_a.lon)
        end_coord = (request.point_b.lat, request.point_b.lon)

        # 2. Candidate departures and how far ahead the risk map must reach
        window_hours = (window_end - window_start).total_seconds() / 3600.0
        interval_hours = max(request.interval_hours, math.ceil(window_hours / (MAX_CANDIDATE_DEPARTURES - 1)) if window_hours > 0 else 1)
        direct_km = haversine_distance(*start_coord, *end_coord)
        speed_kmh = vessel.max_speed_knots * 1.852
        # Allow for detours and ice slow-down: ~2x the direct transit time, 3-10 days.
        voyage_allowance_h = min(240.0, max(72.0, 2.0 * direct_km / speed_kmh))
        duration_hours = int(math.ceil(window_hours + voyage_allowance_h))

        # 3. Grid covering the Antarctic, expanded if the points are outside it
        lat_min = max(-89.5, min(-78.0, request.point_a.lat - 5.0, request.point_b.lat - 5.0))
        lat_max = min(89.5, max(-55.0, request.point_a.lat + 5.0, request.point_b.lat + 5.0))
        config = RiskMapConfig(lat_min=lat_min, lat_max=lat_max, lon_min=-180.0, lon_max=180.0,
                               resolution_deg=0.5, time_step_hours=6)

        # 4. Live icebergs
        from antarctic_dss.data.usnic_live import fetch_current_icebergs
        try:
            live_icebergs = fetch_current_icebergs()
            if 'geom_3031' in live_icebergs.columns:
                live_icebergs = live_icebergs.drop(columns=['geom_3031'])
            live_icebergs = live_icebergs.to_crs(epsg=4326)
            icebergs_geojson = json.loads(live_icebergs.to_json())
            live_iceberg_coords = [(row.geometry.y, row.geometry.x) for _, row in live_icebergs.iterrows()]
        except Exception as e:
            print(f"Failed to fetch live icebergs: {e}")
            icebergs_geojson = {'type': 'FeatureCollection', 'features': []}
            live_iceberg_coords = []

        # 5. Cached environmental forecast (Zarr) -> time-dependent risk slices
        env_data: Dict[str, Any] = {'sic': 0.1, 'wind_speed': 5.0, 'depth_m': 1000.0}
        if FORECAST_ZARR.exists():
            import xarray as xr
            env_data['dataset'] = xr.open_zarr(FORECAST_ZARR)

        # 5b. Iceberg positions over time: predicted drift if the model has proven better than
        #     assuming icebergs stay put, otherwise their current (last observed) positions.
        iceberg_positions, iceberg_mode = live_iceberg_coords, 'current'
        if live_iceberg_coords:
            try:
                iceberg_positions = _predicted_positions(window_start, duration_hours)
                if iceberg_positions is not None:
                    iceberg_mode = 'predicted'
                else:
                    iceberg_positions = live_iceberg_coords
            except Exception as e:
                print(f"Iceberg drift prediction failed, using current positions: {e}")
                iceberg_positions = live_iceberg_coords

        risk_map = TimeDependentRiskMap(config=config)
        from antarctic_dss.routing.bathymetry import depth_on_grid
        depth = depth_on_grid(risk_map.lat_grid, risk_map.lon_grid, config.resolution_deg)
        if depth is not None:
            env_data['real_depth_m'] = depth
        risk_map.build_all_slices(
            start_time=window_start,
            duration_hours=duration_hours,
            env_data=env_data,
            iceberg_trajectories=iceberg_positions,
            vessel=vessel,
        )
        grid = RoutingGrid(risk_map=risk_map, land_mask=_build_land_mask(risk_map),
                           blocked_edges=_build_blocked_edges(risk_map))

        # 6. Sweep candidate departure times, running A* for each
        raw_options = evaluate_departure_window(
            grid=grid,
            vessel=vessel,
            start=start_coord,
            goal=end_coord,
            window_start=window_start,
            window_end=window_end,
            interval_hours=interval_hours,
        )

        # 7. Format for response (evaluate_departure_window returns only failures if nothing succeeded)
        succeeded = [o for o in raw_options if o.distance_km > 0 or o.travel_time_hours > 0]
        direct_line_icebergs = _icebergs_near(
            great_circle_points(*start_coord, *end_coord, spacing_km=10.0), live_iceberg_coords)

        options = []
        for opt in succeeded[:MAX_OPTIONS_RETURNED]:
            near_route = _icebergs_near(_densify(opt.route.path), live_iceberg_coords)
            options.append({
                'departure_time': opt.departure_time,
                'risk_summary': opt.risk_summary,
                'eta': opt.eta,
                'travel_time_hours': opt.route.total_time_hours,
                'distance_km': opt.route.total_distance_km,
                'max_ice_concentration_en_route': opt.route.max_ice_exposure,
                'iceberg_proximity_events': opt.route.iceberg_proximity_events,
                'icebergs_avoided': len(direct_line_icebergs - near_route),
                'prediction_confidence': opt.prediction_confidence,
                'route_geojson': {
                    'type': 'FeatureCollection',
                    'features': [_line_feature(opt.route.path, {
                        'risk': opt.route.route_risk_score,
                        'departure_time': opt.departure_time.isoformat(),
                    })],
                },
            })

        if options:
            best, fastest = options[0], min(options, key=lambda o: o['travel_time_hours'])
            comparison_summary = {
                'message': f"Evaluated {len(raw_options)} departure times; best departure "
                           f"{best['departure_time'].isoformat()} ({best['risk_summary']} risk, "
                           f"{best['travel_time_hours']:.1f} h).",
                'candidates_evaluated': len(raw_options),
                'interval_hours': interval_hours,
                'best_departure_time': best['departure_time'],
                'fastest_departure_time': fastest['departure_time'],
                'fastest_travel_time_hours': fastest['travel_time_hours'],
                'iceberg_positions': iceberg_mode,
            }
        else:
            # A* found no path for any departure (e.g. landlocked or ice-blocked): report why.
            fail_reason = raw_options[0].risk_summary if raw_options and raw_options[0].risk_summary else 'Failed'
            options.append({
                'departure_time': window_start,
                'risk_summary': fail_reason,
                'eta': window_end,
                'travel_time_hours': 0,
                'distance_km': 0,
                'max_ice_concentration_en_route': 0,
                'iceberg_proximity_events': 0,
                'prediction_confidence': 0,
                'route_geojson': {
                    'type': 'FeatureCollection',
                    'features': [_line_feature([start_coord, end_coord], {})],
                },
            })
            comparison_summary = {'message': f'No route found: {fail_reason}',
                                  'candidates_evaluated': len(raw_options)}

        result = VoyageResultSchema(
            id=voyage_id,
            status='completed' if succeeded else 'failed',
            options=options,
            icebergs_geojson=icebergs_geojson,
            comparison_summary=comparison_summary,
        )

        _voyage_results[voyage_id] = result
        return result
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@router.get('/{voyage_id}/options', response_model=VoyageResultSchema)
def get_voyage_options(voyage_id: str) -> VoyageResultSchema:
    """Get departure-time comparison results for a planned voyage."""
    if voyage_id not in _voyage_results:
        raise HTTPException(status_code=404, detail='Voyage not found')
    return _voyage_results[voyage_id]
