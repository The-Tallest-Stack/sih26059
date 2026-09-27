from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import List, Optional, Callable, Dict, Any

from antarctic_dss.routing.vessel import VesselProfile
from antarctic_dss.routing.astar import RouteResult, RoutingGrid, time_dependent_astar
from antarctic_dss.routing.risk_map import TimeDependentRiskMap

@dataclass
class DepartureOption:
    departure_time: datetime
    route: RouteResult
    risk_summary: str
    eta: datetime
    travel_time_hours: float
    distance_km: float
    max_ice_concentration_en_route: float
    iceberg_proximity_events: int
    prediction_confidence: float
    data_freshness: Dict[str, str]

def classify_risk(risk_score: float) -> str:
    """Classify numeric risk score into categorical string."""
    if risk_score < 0.3:
        return 'Low'
    if risk_score < 0.7:
        return 'Medium'
    return 'High'

def compute_confidence(departure_time: datetime, route: RouteResult) -> float:
    """Compute confidence based on forecast horizon."""
    now = datetime.utcnow()
    # Ensure forecast horizon is positive
    horizon_days = max(0.0, (departure_time - now).total_seconds() / 86400.0)
    base_confidence = 0.95
    confidence = base_confidence - (0.03 * horizon_days)
    return max(0.3, min(0.95, confidence))

def evaluate_departure_window(
    grid: RoutingGrid,
    vessel: VesselProfile,
    start: tuple[float, float],
    goal: tuple[float, float],
    window_start: datetime,
    window_end: datetime,
    interval_hours: int = 6,
    env_data_loader: Optional[Callable] = None,
    trajectory_predictor: Optional[Callable] = None,
) -> List[DepartureOption]:
    
    options = []
    current_time = window_start
    while current_time <= window_end:
        # Mock environment steps
        # In real code:
        # env_data = env_data_loader(...)
        # trajectories = trajectory_predictor(...)
        # grid.risk_map.build_all_slices(...)
        
        route = time_dependent_astar(grid, vessel, start, goal, current_time)
        if route:
            eta = current_time + timedelta(hours=route.total_time_hours)
            conf = compute_confidence(current_time, route)
            opt = DepartureOption(
                departure_time=current_time,
                route=route,
                risk_summary=classify_risk(route.route_risk_score),
                eta=eta,
                travel_time_hours=route.total_time_hours,
                distance_km=route.total_distance_km,
                max_ice_concentration_en_route=route.max_ice_exposure,
                iceberg_proximity_events=route.iceberg_proximity_events,
                prediction_confidence=conf,
                data_freshness={}
            )
            options.append(opt)
            
        current_time += timedelta(hours=interval_hours)
        
    options.sort(key=lambda x: x.route.route_risk_score)
    return options

def compare_options(options: List[DepartureOption]) -> Dict[str, Any]:
    if not options:
        return {}
        
    best_time = min(options, key=lambda x: x.route.route_risk_score).departure_time
    lowest_risk = min(options, key=lambda x: x.route.route_risk_score)
    shortest_time = min(options, key=lambda x: x.travel_time_hours)
    
    return {
        'best_time': best_time,
        'lowest_risk': lowest_risk,
        'shortest_time': shortest_time,
        'trade_off_summary': f"Best departure is {best_time}. Shortest travel time is {shortest_time.travel_time_hours:.1f} hours."
    }

def to_geojson_collection(options: List[DepartureOption]) -> Dict[str, Any]:
    features = []
    for opt in options:
        coords = [[lon, lat] for lat, lon in opt.route.path]
        features.append({
            "type": "Feature",
            "geometry": {
                "type": "LineString",
                "coordinates": coords
            },
            "properties": {
                "departure_time": opt.departure_time.isoformat(),
                "risk_summary": opt.risk_summary,
                "travel_time_hours": opt.travel_time_hours,
                "distance_km": opt.distance_km,
                "confidence": opt.prediction_confidence
            }
        })
        
    return {
        "type": "FeatureCollection",
        "features": features
    }
