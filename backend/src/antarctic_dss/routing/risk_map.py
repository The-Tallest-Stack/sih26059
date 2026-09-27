from dataclasses import dataclass, field
import numpy as np
from datetime import datetime, timedelta
from typing import Optional, Dict, Tuple
from antarctic_dss.routing.vessel import VesselProfile

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

class TimeDependentRiskMap:
    """
    Dynamic time-dependent risk map for pathfinding.
    """
    def __init__(self, config: Optional[RiskMapConfig] = None, weights: Optional[RiskWeights] = None):
        self.config = config or RiskMapConfig()
        self.weights = weights or RiskWeights()
        
        self.n_lat = int(np.ceil((self.config.lat_max - self.config.lat_min) / self.config.resolution_deg)) + 1
        self.n_lon = int(np.ceil((self.config.lon_max - self.config.lon_min) / self.config.resolution_deg)) + 1
        
        self.lat_grid = np.linspace(self.config.lat_min, self.config.lat_max, self.n_lat)
        self.lon_grid = np.linspace(self.config.lon_min, self.config.lon_max, self.n_lon)
        
        self.cost_grids: Dict[datetime, np.ndarray] = {}

    def _lat_to_idx(self, lat: float) -> int:
        return int(round((lat - self.config.lat_min) / self.config.resolution_deg))
        
    def _lon_to_idx(self, lon: float) -> int:
        return int(round((lon - self.config.lon_min) / self.config.resolution_deg))
        
    def coord_to_idx(self, lat: float, lon: float) -> Tuple[int, int]:
        return self._lat_to_idx(lat), self._lon_to_idx(lon)

    def idx_to_coord(self, lat_idx: int, lon_idx: int) -> Tuple[float, float]:
        return self.lat_grid[lat_idx], self.lon_grid[lon_idx]

    def compute_cell_cost(self, sic: float, iceberg_risk: float, wind_speed: float, wave_height: float, depth_m: float, vessel: VesselProfile) -> float:
        if sic > vessel.max_ice_concentration:
            return np.inf
        if depth_m < (vessel.draft_m + 2.0):
            return np.inf
            
        cost = 0.0
        
        if sic > 0.15:
            cost += self.weights.ice * np.exp(sic * 5.0)
            
        cost += self.weights.iceberg * iceberg_risk
        
        if wind_speed > 15.0:
            cost += self.weights.wind * ((wind_speed - 15.0) ** 2)
            
        if wave_height > 2.0:
            cost += self.weights.wave * ((wave_height - 2.0) ** 2)
            
        return cost

    def build_time_slice(self, time: datetime, env_data: dict, iceberg_trajectories: list, vessel: VesselProfile):
        """
        Build a risk grid for a single time slice.
        """
        grid = np.zeros((self.n_lat, self.n_lon))
        
        # Simulated data unpacking and cost computation
        # In actual usage, query env_data for each cell
        for i in range(self.n_lat):
            for j in range(self.n_lon):
                # Placeholder for cell data extraction
                sic = env_data.get('sic', 0.0)
                iceberg_risk = 0.0
                wind_speed = env_data.get('wind_speed', 0.0)
                wave_height = env_data.get('wave_height', 0.0)
                depth_m = env_data.get('depth_m', 100.0)
                
                grid[i, j] = self.compute_cell_cost(sic, iceberg_risk, wind_speed, wave_height, depth_m, vessel)
                
        self.cost_grids[time] = grid

    def get_cost(self, lat: float, lon: float, time: datetime) -> float:
        if not self.cost_grids:
            return 0.0
            
        times = sorted(self.cost_grids.keys())
        nearest_time = min(times, key=lambda t: abs((t - time).total_seconds()))
        lat_idx, lon_idx = self.coord_to_idx(lat, lon)
        return self.get_cost_by_idx(lat_idx, lon_idx, nearest_time)

    def get_cost_by_idx(self, lat_idx: int, lon_idx: int, time: datetime) -> float:
        if time not in self.cost_grids:
            if not self.cost_grids:
                return 0.0
            times = sorted(self.cost_grids.keys())
            time = min(times, key=lambda t: abs((t - time).total_seconds()))
            
        if 0 <= lat_idx < self.n_lat and 0 <= lon_idx < self.n_lon:
            return self.cost_grids[time][lat_idx, lon_idx]
        return np.inf

    def build_all_slices(self, start_time: datetime, duration_hours: int, env_data: dict, iceberg_trajectories: list, vessel: VesselProfile):
        for h in range(0, duration_hours, self.config.time_step_hours):
            t = start_time + timedelta(hours=h)
            self.build_time_slice(t, env_data, iceberg_trajectories, vessel)

    def to_geojson(self, time: datetime) -> dict:
        features = []
        if time in self.cost_grids:
            grid = self.cost_grids[time]
            for i in range(self.n_lat):
                for j in range(self.n_lon):
                    lat, lon = self.idx_to_coord(i, j)
                    cost = grid[i, j]
                    if cost < np.inf:
                        features.append({
                            "type": "Feature",
                            "geometry": {
                                "type": "Point",
                                "coordinates": [lon, lat]
                            },
                            "properties": {
                                "cost": cost
                            }
                        })
                        
        return {
            "type": "FeatureCollection",
            "features": features
        }
