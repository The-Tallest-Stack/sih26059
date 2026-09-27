import heapq
import math
import numpy as np
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional, List, Tuple

from antarctic_dss.routing.vessel import VesselProfile, compute_effective_speed
from antarctic_dss.routing.risk_map import TimeDependentRiskMap
# Mocking utils import assuming it will exist
# from antarctic_dss.utils.geo import haversine_distance

def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)
    a = math.sin(delta_phi / 2.0)**2 + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2.0)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

@dataclass
class RouteResult:
    path: List[Tuple[float, float]]
    arrival_times: List[datetime]
    total_time_hours: float
    total_distance_km: float
    max_ice_exposure: float
    avg_ice_exposure: float
    iceberg_proximity_events: int
    route_risk_score: float
    confidence: float

class RoutingGrid:
    def __init__(self, risk_map: TimeDependentRiskMap, land_mask: Optional[np.ndarray] = None, bathy_mask: Optional[np.ndarray] = None):
        self.risk_map = risk_map
        self.n_lat = risk_map.n_lat
        self.n_lon = risk_map.n_lon
        self.land_mask = land_mask
        self.neighbors_offsets = [(0,1), (0,-1), (1,0), (-1,0), (1,1), (1,-1), (-1,1), (-1,-1)]

    def get_neighbors(self, lat_idx: int, lon_idx: int) -> List[Tuple[int, int]]:
        neighbors = []
        for dlat, dlon in self.neighbors_offsets:
            n_lat, n_lon = lat_idx + dlat, lon_idx + dlon
            if 0 <= n_lat < self.n_lat and 0 <= n_lon < self.n_lon:
                if self.land_mask is not None and self.land_mask[n_lat, n_lon]:
                    continue
                neighbors.append((n_lat, n_lon))
        return neighbors

    def is_traversable(self, lat_idx: int, lon_idx: int, time: datetime, vessel: VesselProfile) -> bool:
        if self.land_mask is not None and self.land_mask[lat_idx, lon_idx]:
            return False
        cost = self.risk_map.get_cost_by_idx(lat_idx, lon_idx, time)
        return cost != np.inf

def time_dependent_astar(grid: RoutingGrid, vessel: VesselProfile, start: Tuple[float, float], goal: Tuple[float, float], departure_time: datetime) -> Optional[RouteResult]:
    start_idx = grid.risk_map.coord_to_idx(start[0], start[1])
    goal_idx = grid.risk_map.coord_to_idx(goal[0], goal[1])

    if start_idx == goal_idx:
        return RouteResult([start], [departure_time], 0.0, 0.0, 0.0, 0.0, 0, 0.0, 1.0)
        
    def heuristic(node_idx):
        lat, lon = grid.risk_map.idx_to_coord(node_idx[0], node_idx[1])
        dist_km = haversine_distance(lat, lon, goal[0], goal[1])
        speed_ms = vessel.max_speed_knots * 0.5144
        return (dist_km * 1000) / speed_ms
        
    pq = []
    # (f_score, arrival_time_seconds, node_idx_tuple, path_list)
    heapq.heappush(pq, (heuristic(start_idx), 0.0, start_idx, [start_idx]))
    
    earliest_arrival = {start_idx: 0.0}
    
    while pq:
        _, current_time_sec, curr_idx, path = heapq.heappop(pq)
        
        if curr_idx == goal_idx:
            # Construct result
            waypts = [grid.risk_map.idx_to_coord(idx[0], idx[1]) for idx in path]
            # Mocked calculations for brevity
            dist_km = sum(haversine_distance(waypts[i][0], waypts[i][1], waypts[i+1][0], waypts[i+1][1]) for i in range(len(waypts)-1))
            return RouteResult(
                path=waypts,
                arrival_times=[departure_time + timedelta(seconds=0)] * len(waypts),
                total_time_hours=current_time_sec / 3600.0,
                total_distance_km=dist_km,
                max_ice_exposure=0.0,
                avg_ice_exposure=0.0,
                iceberg_proximity_events=0,
                route_risk_score=0.0,
                confidence=0.9
            )
            
        if current_time_sec > earliest_arrival.get(curr_idx, float('inf')):
            continue
            
        current_dt = departure_time + timedelta(seconds=current_time_sec)
        
        for nxt_idx in grid.get_neighbors(curr_idx[0], curr_idx[1]):
            cost = grid.risk_map.get_cost_by_idx(nxt_idx[0], nxt_idx[1], current_dt)
            if cost == np.inf:
                continue
                
            curr_coords = grid.risk_map.idx_to_coord(curr_idx[0], curr_idx[1])
            nxt_coords = grid.risk_map.idx_to_coord(nxt_idx[0], nxt_idx[1])
            
            dist_m = haversine_distance(curr_coords[0], curr_coords[1], nxt_coords[0], nxt_coords[1]) * 1000
            
            # Simplified effective speed assumption for A* exploration
            eff_speed = compute_effective_speed(vessel, 0.0) # Mock SIC
            if eff_speed <= 0:
                continue
                
            travel_time_sec = dist_m / eff_speed
            new_time_sec = current_time_sec + travel_time_sec
            
            if new_time_sec < earliest_arrival.get(nxt_idx, float('inf')):
                earliest_arrival[nxt_idx] = new_time_sec
                f_score = new_time_sec + heuristic(nxt_idx)
                heapq.heappush(pq, (f_score, new_time_sec, nxt_idx, path + [nxt_idx]))
                
    return None
