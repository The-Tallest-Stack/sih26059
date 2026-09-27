from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Callable
import pandas as pd
from antarctic_dss.models.xgboost_model import IcebergDisplacementModel
from antarctic_dss.models.uncertainty import UncertaintyEstimator
from antarctic_dss.models.physics_baseline import free_drift_displacement
from antarctic_dss.utils.geo import epsg3031_to_epsg4326, epsg4326_to_epsg3031

@dataclass
class TrajectoryPoint:
    time: datetime
    lat: float
    lon: float
    x_3031: float
    y_3031: float
    horizon_hours: int
    uncertainty_radius_km: float

@dataclass
class IcebergTrajectory:
    iceberg_id: str
    start_time: datetime
    start_lat: float
    start_lon: float
    points: List[TrajectoryPoint]

DEFAULT_HORIZONS = [6, 12, 18, 24, 48, 72]

class TrajectoryGenerator:
    """
    Multi-horizon trajectory generator.
    """
    def __init__(self, model: IcebergDisplacementModel, uncertainty_estimator: Optional[UncertaintyEstimator] = None):
        self.model = model
        self.uncertainty_estimator = uncertainty_estimator or UncertaintyEstimator()
        
    def predict_trajectory(self, iceberg_state: Dict, env_forecast_sampler: Callable, horizons_hours: Optional[List[int]] = None) -> IcebergTrajectory:
        if horizons_hours is None:
            horizons_hours = DEFAULT_HORIZONS
            
        points = []
        current_time = iceberg_state['time']
        start_time = current_time
        
        start_lat = iceberg_state['lat']
        start_lon = iceberg_state['lon']
        current_x, current_y = epsg4326_to_epsg3031(start_lat, start_lon)
        
        lag1_dx = iceberg_state.get('lag1_dx', 0.0)
        lag1_dy = iceberg_state.get('lag1_dy', 0.0)
        
        prev_time = start_time
        
        for horizon in sorted(horizons_hours):
            target_time = start_time + timedelta(hours=horizon)
            dt_seconds = (target_time - prev_time).total_seconds()
            
            env = env_forecast_sampler(current_x, current_y, target_time)
            
            physics_dx, physics_dy = free_drift_displacement(
                wind_u=env['wind_u'], wind_v=env['wind_v'],
                current_u=env['ocean_current_u'], current_v=env['ocean_current_v'],
                seaice_drift_u=env['seaice_drift_u'], seaice_drift_v=env['seaice_drift_v'],
                seaice_concentration=env['seaice_concentration'],
                dt_seconds=dt_seconds
            )
            
            current_lat, current_lon = epsg3031_to_epsg4326(current_x, current_y)
            
            features = {
                'lat': current_lat,
                'lon': current_lon,
                'size_km2': iceberg_state.get('size_km2', 1.0),
                'disp_km': (dt_seconds / 86400.0) * 10.0, # dummy approximation if needed
                'wind_u': env['wind_u'],
                'wind_v': env['wind_v'],
                'ocean_current_u': env['ocean_current_u'],
                'ocean_current_v': env['ocean_current_v'],
                'seaice_drift_u': env['seaice_drift_u'],
                'seaice_drift_v': env['seaice_drift_v'],
                'seaice_concentration': env['seaice_concentration'],
                'lag1_dx': lag1_dx,
                'lag1_dy': lag1_dy,
                'month_sin': iceberg_state.get('month_sin', 0.0),
                'month_cos': iceberg_state.get('month_cos', 1.0),
                'physics_pred_dx': physics_dx,
                'physics_pred_dy': physics_dy
            }
            
            pred_dx, pred_dy = self.model.predict_single(features)
            
            current_x += pred_dx
            current_y += pred_dy
            
            lag1_dx = pred_dx
            lag1_dy = pred_dy
            
            current_lat, current_lon = epsg3031_to_epsg4326(current_x, current_y)
            
            unc_radius = self.uncertainty_estimator.estimate(horizon, env['seaice_concentration'])
            
            points.append(TrajectoryPoint(
                time=target_time,
                lat=current_lat,
                lon=current_lon,
                x_3031=current_x,
                y_3031=current_y,
                horizon_hours=horizon,
                uncertainty_radius_km=unc_radius
            ))
            
            prev_time = target_time
            
        return IcebergTrajectory(
            iceberg_id=iceberg_state['iceberg_id'],
            start_time=start_time,
            start_lat=start_lat,
            start_lon=start_lon,
            points=points
        )
        
    def predict_all_icebergs(self, iceberg_states: List[Dict], env_forecast_sampler: Callable) -> List[IcebergTrajectory]:
        return [self.predict_trajectory(state, env_forecast_sampler) for state in iceberg_states]
        
    def to_geojson(self, trajectory: IcebergTrajectory) -> Dict:
        coordinates = [[trajectory.start_lon, trajectory.start_lat]]
        horizons = [0]
        uncertainties = [0.0]
        
        for p in trajectory.points:
            coordinates.append([p.lon, p.lat])
            horizons.append(p.horizon_hours)
            uncertainties.append(p.uncertainty_radius_km)
            
        return {
            "type": "Feature",
            "geometry": {
                "type": "LineString",
                "coordinates": coordinates
            },
            "properties": {
                "iceberg_id": trajectory.iceberg_id,
                "start_time": trajectory.start_time.isoformat(),
                "horizons": horizons,
                "uncertainties": uncertainties
            }
        }
        
    def all_to_geojson(self, trajectories: List[IcebergTrajectory]) -> Dict:
        features = [self.to_geojson(t) for t in trajectories]
        return {
            "type": "FeatureCollection",
            "features": features
        }
