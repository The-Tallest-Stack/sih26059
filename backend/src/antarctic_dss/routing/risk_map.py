import bisect
from dataclasses import dataclass
import numpy as np
from datetime import datetime, timedelta
from typing import Optional, Dict, Tuple, List
import xarray as xr
from antarctic_dss.routing.vessel import VesselProfile
from antarctic_dss.utils.geo import haversine_km_array

# Distance within which an iceberg counts as a navigational hazard for a cell / waypoint.
ICEBERG_PROXIMITY_KM = 60.0
# Per-iceberg risk added to a cell inside the proximity radius (multiplied by RiskWeights.iceberg).
ICEBERG_CELL_RISK = 1000.0
# Minimum under-keel clearance in metres.
UKC_MARGIN_M = 2.0
# Assumed ice thickness where the forecast has concentration but no thickness.
NOMINAL_ICE_THICKNESS_M = 1.0
# Forecast steps further than this from a slice's time are not used for it.
MAX_FORECAST_TIME_GAP = np.timedelta64(36, 'h')

@dataclass
class RiskWeights:
    ice: float = 10.0
    iceberg: float = 20.0
    wind: float = 3.0
    wave: float = 5.0
    depth: float = 2.0

@dataclass
class RiskMapConfig:
    lat_min: float = -78.0
    lat_max: float = -55.0
    lon_min: float = -180.0
    lon_max: float = 180.0
    resolution_deg: float = 0.25
    time_step_hours: int = 6

@dataclass
class EnvSlice:
    """Environmental layers for one time slice, kept so routes can report real exposure metrics."""
    sic: np.ndarray
    wind_speed: np.ndarray
    wave_height: np.ndarray
    iceberg_count: np.ndarray
    from_real_data: bool
    ice_thickness: Optional[np.ndarray] = None

class TimeDependentRiskMap:
    """
    Dynamic time-dependent risk map for pathfinding.

    When the configured longitude range spans the full globe, the grid wraps: the last
    column neighbours the first, so routes can cross the antimeridian.
    """
    def __init__(self, config: Optional[RiskMapConfig] = None, weights: Optional[RiskWeights] = None):
        self.config = config or RiskMapConfig()
        self.weights = weights or RiskWeights()
        res = self.config.resolution_deg

        self.wrap_lon = (self.config.lon_max - self.config.lon_min) >= 360.0 - 1e-9

        self.n_lat = int(np.ceil((self.config.lat_max - self.config.lat_min) / res)) + 1
        self.lat_grid = np.linspace(self.config.lat_min, self.config.lat_max, self.n_lat)

        if self.wrap_lon:
            # -180 and 180 are the same meridian: don't duplicate it.
            self.n_lon = int(round(360.0 / res))
            self.lon_grid = self.config.lon_min + np.arange(self.n_lon) * res
        else:
            self.n_lon = int(np.ceil((self.config.lon_max - self.config.lon_min) / res)) + 1
            self.lon_grid = np.linspace(self.config.lon_min, self.config.lon_max, self.n_lon)

        self.cost_grids: Dict[datetime, np.ndarray] = {}
        self.env_slices: Dict[datetime, EnvSlice] = {}
        self._sorted_times: List[datetime] = []

    def _lat_to_idx(self, lat: float) -> int:
        return int(round((lat - self.config.lat_min) / self.config.resolution_deg))

    def _lon_to_idx(self, lon: float) -> int:
        if self.wrap_lon:
            offset = (lon - self.config.lon_min) % 360.0
            return int(round(offset / self.config.resolution_deg)) % self.n_lon
        return int(round((lon - self.config.lon_min) / self.config.resolution_deg))

    def coord_to_idx(self, lat: float, lon: float) -> Tuple[int, int]:
        return self._lat_to_idx(lat), self._lon_to_idx(lon)

    def idx_to_coord(self, lat_idx: int, lon_idx: int) -> Tuple[float, float]:
        return float(self.lat_grid[lat_idx]), float(self.lon_grid[lon_idx])

    def compute_cost_array(self, sic, iceberg_risk, wind_speed, wave_height, depth_m, vessel: VesselProfile,
                           ice_thickness=0.0) -> np.ndarray:
        """Vectorised cell cost. np.inf marks impassable cells (ice too dense/thick, or too shallow)."""
        sic, iceberg_risk, wind_speed, wave_height, depth_m, ice_thickness = np.broadcast_arrays(
            *(np.asarray(v, dtype=float) for v in (sic, iceberg_risk, wind_speed, wave_height, depth_m, ice_thickness)))
        cost = np.zeros(sic.shape, dtype=float)
        # Ice risk depends on the ice relative to the vessel's capability: concentration scaled
        # by thickness / rated thickness (unknown thickness assumed to be typical 1 m first-year ice).
        # A heavy icebreaker in 1 m ice sees little risk; a light ice class sees a lot.
        if np.isfinite(vessel.max_ice_thickness_m):
            thickness = np.where(ice_thickness > 0, ice_thickness, NOMINAL_ICE_THICKNESS_M)
            severity = sic * np.minimum(1.0, thickness / vessel.max_ice_thickness_m)
        else:
            severity = sic
        cost += np.where(sic > 0.15, self.weights.ice * np.exp(severity * 5.0), 0.0)
        cost += self.weights.iceberg * iceberg_risk
        cost += np.where(wind_speed > 15.0, self.weights.wind * (wind_speed - 15.0) ** 2, 0.0)
        cost += np.where(wave_height > 2.0, self.weights.wave * (wave_height - 2.0) ** 2, 0.0)
        impassable = ((sic > vessel.max_ice_concentration) | (depth_m < vessel.draft_m + UKC_MARGIN_M)
                      | ((sic > 0.15) & (ice_thickness > vessel.max_ice_thickness_m)))
        cost[impassable] = np.inf
        return cost

    def compute_cell_cost(self, sic: float, iceberg_risk: float, wind_speed: float, wave_height: float, depth_m: float,
                          vessel: VesselProfile, ice_thickness: float = 0.0) -> float:
        return float(self.compute_cost_array(sic, iceberg_risk, wind_speed, wave_height, depth_m, vessel, ice_thickness))

    def _mesh(self) -> Tuple[np.ndarray, np.ndarray]:
        return np.meshgrid(self.lat_grid, self.lon_grid, indexing='ij')

    def build_time_slice(self, time: datetime, env_data: dict, iceberg_trajectories: list, vessel: VesselProfile):
        """
        Build a risk grid for a single time slice.

        env_data may contain scalar defaults ('sic', 'wind_speed', 'wave_height', 'depth_m'),
        gridded overrides ('real_sic', 'real_wind_speed', 'real_wave_height', 'real_depth_m';
        NaN cells fall back to the scalar default), or a synthetic storm ('storm_lat', 'storm_lon')
        used only when no real sea-ice data is available.
        """
        shape = (self.n_lat, self.n_lon)
        lat, lon = self._mesh()

        def layer(name: str, default: float) -> np.ndarray:
            base = np.full(shape, float(env_data.get(name, default)))
            real = env_data.get(f'real_{name}')
            if real is not None:
                real = np.asarray(real, dtype=float)
                base = np.where(np.isnan(real), base, real)
            return base

        sic = layer('sic', 0.0)
        wind_speed = layer('wind_speed', 0.0)
        wave_height = layer('wave_height', 0.0)
        depth_m = layer('depth_m', 1000.0)
        ice_thickness = layer('ice_thickness', 0.0)
        from_real_data = env_data.get('real_sic') is not None

        storm_lat, storm_lon = env_data.get('storm_lat'), env_data.get('storm_lon')
        if not from_real_data and storm_lat is not None and storm_lon is not None:
            dist_to_storm = haversine_km_array(lat, lon, storm_lat, storm_lon)
            intensity = np.clip(1.0 - dist_to_storm / 800.0, 0.0, 1.0)  # 800 km storm radius
            wind_speed = wind_speed + 30.0 * intensity ** 2
            wave_height = wave_height + 10.0 * intensity ** 2
            sic = np.where(intensity > 0, np.minimum(0.95, sic + 0.8 * intensity), sic)

        iceberg_count = np.zeros(shape, dtype=np.int32)
        # Each entry is (lat, lon) or (lat, lon, extra_radius_km), e.g. prediction uncertainty.
        for position in iceberg_trajectories:
            ice_lat, ice_lon = position[0], position[1]
            radius = ICEBERG_PROXIMITY_KM + (position[2] if len(position) > 2 else 0.0)
            iceberg_count += haversine_km_array(lat, lon, ice_lat, ice_lon) < radius

        self.cost_grids[time] = self.compute_cost_array(
            sic, iceberg_count * ICEBERG_CELL_RISK, wind_speed, wave_height, depth_m, vessel, ice_thickness)
        self.env_slices[time] = EnvSlice(sic, wind_speed, wave_height, iceberg_count, from_real_data, ice_thickness)
        self._sorted_times = sorted(self.cost_grids.keys())

    def nearest_time(self, time: datetime) -> Optional[datetime]:
        """Nearest built slice time (slices are rebuilt/added rarely, lookups are hot)."""
        times = self._sorted_times
        if len(times) != len(self.cost_grids):
            times = self._sorted_times = sorted(self.cost_grids.keys())
        if not times:
            return None
        i = bisect.bisect_left(times, time)
        if i == 0:
            return times[0]
        if i == len(times):
            return times[-1]
        before, after = times[i - 1], times[i]
        return after if (after - time) < (time - before) else before

    def get_cost(self, lat: float, lon: float, time: datetime) -> float:
        if not self.cost_grids:
            return 0.0
        lat_idx, lon_idx = self.coord_to_idx(lat, lon)
        return self.get_cost_by_idx(lat_idx, lon_idx, time)

    def get_cost_by_idx(self, lat_idx: int, lon_idx: int, time: datetime) -> float:
        if time not in self.cost_grids:
            time = self.nearest_time(time)
            if time is None:
                return 0.0
        if 0 <= lat_idx < self.n_lat and 0 <= lon_idx < self.n_lon:
            return self.cost_grids[time][lat_idx, lon_idx]
        return np.inf

    def get_env_slice(self, time: datetime) -> Optional[EnvSlice]:
        t = time if time in self.env_slices else self.nearest_time(time)
        return self.env_slices.get(t) if t is not None else None

    def _sample_dataset(self, ds: xr.Dataset, t: datetime) -> Dict[str, np.ndarray]:
        """Nearest-neighbour sample of a forecast dataset onto this grid at time t."""
        slice_ds = ds.sel(time=np.datetime64(t.replace(tzinfo=None)), method='nearest')
        lat_da = xr.DataArray(self.lat_grid, dims='lat')
        lon_da = xr.DataArray(self.lon_grid, dims='lon')
        interp_ds = slice_ds.sel(latitude=lat_da, longitude=lon_da, method='nearest')
        sampled = {}
        if 'siconc' in interp_ds:
            sampled['real_sic'] = interp_ds['siconc'].values
        if 'wind_u' in interp_ds and 'wind_v' in interp_ds:
            sampled['real_wind_speed'] = np.hypot(interp_ds['wind_u'].values, interp_ds['wind_v'].values)
        if 'swh' in interp_ds:
            sampled['real_wave_height'] = interp_ds['swh'].values
        if 'sithick' in interp_ds:
            sampled['real_ice_thickness'] = interp_ds['sithick'].values

        # 'nearest' clamps to the dataset edge; rows outside its latitude coverage have no data.
        ds_lat = ds['latitude'].values
        half_step = abs(float(ds_lat[1] - ds_lat[0])) / 2 if len(ds_lat) > 1 else 0.0
        outside = (self.lat_grid < ds_lat.min() - half_step) | (self.lat_grid > ds_lat.max() + half_step)
        for key in sampled:
            sampled[key] = np.array(sampled[key], dtype=float)
            sampled[key][outside, :] = np.nan
        return sampled

    def build_all_slices(self, start_time: datetime, duration_hours: int, env_data: dict, iceberg_trajectories: list, vessel: VesselProfile):
        ds = env_data.get('dataset')
        sample_cache: Dict[np.datetime64, Dict[str, np.ndarray]] = {}

        for h in range(0, duration_hours + 1, self.config.time_step_hours):
            t = start_time + timedelta(hours=h)
            custom_env = env_data.copy()

            if ds is not None:
                try:
                    # Forecast data is coarser in time than our slices; sample each source step once.
                    t64 = np.datetime64(t.replace(tzinfo=None))
                    ds_time = ds['time'].sel(time=t64, method='nearest').values[()]
                    # Beyond the forecast's coverage, fall back to defaults rather than reusing
                    # the edge time step as if it were valid (slices are then flagged not-real).
                    if abs(ds_time - t64) <= MAX_FORECAST_TIME_GAP:
                        if ds_time not in sample_cache:
                            sample_cache[ds_time] = self._sample_dataset(ds, t)
                        custom_env.update(sample_cache[ds_time])
                except Exception as e:
                    print(f"Failed to interpolate real data: {e}")
            else:
                # Procedural storm (demo only, used when no forecast cache exists)
                custom_env['storm_lon'] = -70.0 + (h * 0.5)
                custom_env['storm_lat'] = -60.0

            # iceberg_trajectories: a static list of positions, or a callable time -> positions
            # (predicted drift), evaluated per slice.
            positions = iceberg_trajectories(t) if callable(iceberg_trajectories) else iceberg_trajectories
            self.build_time_slice(t, custom_env, positions, vessel)

    def to_geojson(self, time: datetime) -> dict:
        features = []
        if time in self.cost_grids:
            grid = self.cost_grids[time]
            for i, j in zip(*np.nonzero(np.isfinite(grid))):
                lat, lon = self.idx_to_coord(i, j)
                features.append({
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": [lon, lat]},
                    "properties": {"cost": float(grid[i, j])}
                })
        return {"type": "FeatureCollection", "features": features}
