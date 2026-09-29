from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Callable, Dict, Any

from antarctic_dss.routing.vessel import VesselProfile
from antarctic_dss.routing.astar import RouteResult, RoutingGrid, RouteNotFoundError, find_route
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
    """Classify numeric risk score into categorical string.

    The score is rounded to 2 decimals first, so near-identical routes (e.g. 0.2995 vs 0.3001)
    don't get different labels from meaningless differences at a threshold.
    """
    risk_score = round(risk_score, 2)
    if risk_score < 0.3:
        return 'Low'
    if risk_score < 0.7:
        return 'Medium'
    return 'High'

def compute_confidence(departure_time: datetime, route: RouteResult) -> float:
    """Compute confidence based on forecast horizon."""
    now = datetime.now(timezone.utc)
    if departure_time.tzinfo is None:
        departure_time = departure_time.replace(tzinfo=timezone.utc)
    # Ensure forecast horizon is positive
    horizon_days = max(0.0, (departure_time - now).total_seconds() / 86400.0)
    base_confidence = 0.95
    confidence = base_confidence - (0.03 * horizon_days)
    # A route planned on synthetic/fallback environment data can't be more certain than its inputs.
    confidence = min(confidence, route.confidence)
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
    failed_options = []
    current_time = window_start
    while current_time <= window_end:
        try:
            route = find_route(grid, vessel, start, goal, current_time)
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
        except RouteNotFoundError as e:
            opt = DepartureOption(
                departure_time=current_time,
                route=RouteResult([start, goal], [current_time, current_time], 0, 0, 0, 0, 0, 0, 0),
                risk_summary=str(e),
                eta=current_time,
                travel_time_hours=0,
                distance_km=0,
                max_ice_concentration_en_route=0,
                iceberg_proximity_events=0,
                prediction_confidence=0.0,
                data_freshness={}
            )
            failed_options.append(opt)
            
        current_time += timedelta(hours=interval_hours)
        
    if not options:
        return failed_options
        
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
