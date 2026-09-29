import heapq
import numpy as np
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional, List, Tuple, Dict

from antarctic_dss.routing.vessel import VesselProfile, compute_effective_speed
from antarctic_dss.routing.risk_map import TimeDependentRiskMap
from antarctic_dss.utils.geo import haversine_distance

# How strongly A* trades extra travel time for lower risk: an edge through a cell with risk
# cost C is weighted as travel_time * (1 + RISK_AVERSION * C). With the default RiskWeights,
# 50% sea ice roughly doubles an edge's weight and an iceberg's proximity zone multiplies it
# ~200x, so routes detour around icebergs unless there is no alternative.
DEFAULT_RISK_AVERSION = 0.01

# Thresholds used to score weather exposure along a route.
WIND_LIMIT_MS = 15.0
WAVE_LIMIT_M = 2.0

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

class RouteNotFoundError(ValueError):
    """Raised by find_route with a human-readable reason when no route exists."""

class RoutingGrid:
    def __init__(self, risk_map: TimeDependentRiskMap, land_mask: Optional[np.ndarray] = None,
                 bathy_mask: Optional[np.ndarray] = None, blocked_edges: Optional[Dict[Tuple[int, int], np.ndarray]] = None):
        """blocked_edges maps a step direction (dlat, dlon) in EDGE_DIRECTIONS to a bool grid:
        blocked_edges[d][i, j] means the straight segment from cell (i, j) to (i+dlat, j+dlon)
        crosses land (e.g. an island smaller than a cell, which no cell centre falls on)."""
        self.risk_map = risk_map
        self.blocked_edges = blocked_edges
        self.n_lat = risk_map.n_lat
        self.n_lon = risk_map.n_lon
        self.land_mask = land_mask
        self.wrap_lon = risk_map.wrap_lon
        self.neighbors_offsets = [(0,1), (0,-1), (1,0), (-1,0), (1,1), (1,-1), (-1,1), (-1,-1)]

    def _in_bounds(self, lat_idx: int, lon_idx: int) -> Optional[Tuple[int, int]]:
        if not 0 <= lat_idx < self.n_lat:
            return None
        if self.wrap_lon:
            return lat_idx, lon_idx % self.n_lon
        if 0 <= lon_idx < self.n_lon:
            return lat_idx, lon_idx
        return None

    def adjacent(self, lat_idx: int, lon_idx: int) -> List[Tuple[int, int]]:
        """All in-bounds adjacent cells (including land), wrapping longitude on global grids."""
        cells = []
        for dlat, dlon in self.neighbors_offsets:
            cell = self._in_bounds(lat_idx + dlat, lon_idx + dlon)
            if cell is not None:
                cells.append(cell)
        return cells

    def edge_blocked(self, lat_idx: int, lon_idx: int, dlat: int, dlon: int) -> bool:
        if self.blocked_edges is None:
            return False
        if (dlat, dlon) in self.blocked_edges:
            return bool(self.blocked_edges[(dlat, dlon)][lat_idx, lon_idx])
        # Reverse direction: look the edge up from the other end.
        origin = self._in_bounds(lat_idx + dlat, lon_idx + dlon)
        return origin is not None and bool(self.blocked_edges[(-dlat, -dlon)][origin])

    def get_neighbors(self, lat_idx: int, lon_idx: int) -> List[Tuple[int, int]]:
        neighbors = []
        for dlat, dlon in self.neighbors_offsets:
            cell = self._in_bounds(lat_idx + dlat, lon_idx + dlon)
            if cell is None or (self.land_mask is not None and self.land_mask[cell]):
                continue
            if self.edge_blocked(lat_idx, lon_idx, dlat, dlon):
                continue
            neighbors.append(cell)
        return neighbors

    def is_traversable(self, lat_idx: int, lon_idx: int, time: datetime, vessel: VesselProfile) -> bool:
        if self.land_mask is not None and self.land_mask[lat_idx, lon_idx]:
            return False
        cost = self.risk_map.get_cost_by_idx(lat_idx, lon_idx, time)
        return cost != np.inf

def _snap_to_water(grid: RoutingGrid, idx: Tuple[int, int], time: datetime, vessel: VesselProfile, max_steps: int = 10) -> Tuple[int, int]:
    """Move a start/goal cell that lands on land or impassable ice to the nearest traversable cell."""
    if grid.is_traversable(idx[0], idx[1], time, vessel):
        return idx
    queue = deque([(idx, 0)])
    visited = {idx}
    while queue:
        curr, dist = queue.popleft()
        if dist >= max_steps:
            break
        for nx in grid.adjacent(*curr):
            if nx in visited:
                continue
            if grid.is_traversable(nx[0], nx[1], time, vessel):
                return nx
            visited.add(nx)
            queue.append((nx, dist + 1))
    return idx

# Directions stored in RoutingGrid.blocked_edges; the other four are their reverses.
EDGE_DIRECTIONS = [(0, 1), (1, 0), (1, 1), (1, -1)]

def _ice_at(grid: RoutingGrid, idx: Tuple[int, int], time: datetime) -> Tuple[float, float]:
    """(sea-ice concentration, ice thickness m) at a cell for the slice nearest `time`."""
    env = grid.risk_map.get_env_slice(time)
    if env is None:
        return 0.0, 0.0
    thickness = float(env.ice_thickness[idx]) if env.ice_thickness is not None else 0.0
    return float(env.sic[idx]), thickness

def compute_route_metrics(grid: RoutingGrid, vessel: VesselProfile, cells: List[Tuple[int, int]], arrival_times: List[datetime]) -> Dict[str, float]:
    """Ice/iceberg/weather exposure along a route, sampled at each waypoint's arrival time."""
    sics, winds, waves, iceberg_events = [], [], [], 0
    real_data_points = 0
    for cell, t in zip(cells, arrival_times):
        env = grid.risk_map.get_env_slice(t)
        if env is None:
            sics.append(0.0); winds.append(0.0); waves.append(0.0)
            continue
        sics.append(float(env.sic[cell]))
        winds.append(float(env.wind_speed[cell]))
        waves.append(float(env.wave_height[cell]))
        iceberg_events += int(env.iceberg_count[cell] > 0)
        real_data_points += int(env.from_real_data)

    max_ice = max(sics) if sics else 0.0
    avg_ice = float(np.mean(sics)) if sics else 0.0

    # Each component is normalised to [0, 1]; the weighted sum is the route risk score.
    ice_limit = max(vessel.max_ice_concentration, 1e-6)
    ice_component = min(1.0, 0.5 * max_ice / ice_limit + 0.5 * avg_ice / ice_limit)
    iceberg_component = min(1.0, iceberg_events / 3.0)
    wind_excess = max(0.0, (max(winds) if winds else 0.0) - WIND_LIMIT_MS) / 15.0
    wave_excess = max(0.0, (max(waves) if waves else 0.0) - WAVE_LIMIT_M) / 6.0
    weather_component = min(1.0, max(wind_excess, wave_excess))
    risk_score = 0.45 * ice_component + 0.35 * iceberg_component + 0.20 * weather_component

    # Routes planned on the synthetic fallback environment are much less trustworthy.
    data_fraction = real_data_points / len(cells) if cells else 0.0
    confidence = 0.5 + 0.4 * data_fraction

    return {
        'max_ice_exposure': max_ice,
        'avg_ice_exposure': avg_ice,
        'iceberg_proximity_events': iceberg_events,
        'route_risk_score': float(np.clip(risk_score, 0.0, 1.0)),
        'confidence': confidence,
    }

def find_route(grid: RoutingGrid, vessel: VesselProfile, start: Tuple[float, float], goal: Tuple[float, float],
               departure_time: datetime, risk_aversion: float = DEFAULT_RISK_AVERSION) -> RouteResult:
    """Risk-weighted, time-dependent A*. Raises RouteNotFoundError with a reason if no route exists."""
    risk_map = grid.risk_map
    start_idx = _snap_to_water(grid, risk_map.coord_to_idx(*start), departure_time, vessel)
    goal_idx = _snap_to_water(grid, risk_map.coord_to_idx(*goal), departure_time, vessel)

    if not grid.is_traversable(start_idx[0], start_idx[1], departure_time, vessel):
        raise RouteNotFoundError(f"Start point is impassable. Sea Ice concentration likely exceeds vessel class {vessel.name} limits.")
    if not grid.is_traversable(goal_idx[0], goal_idx[1], departure_time, vessel):
        raise RouteNotFoundError(f"Goal point is impassable. Sea Ice concentration likely exceeds vessel class {vessel.name} limits.")

    if start_idx == goal_idx:
        return RouteResult([start, goal], [departure_time, departure_time], 0.0,
                           haversine_distance(start[0], start[1], goal[0], goal[1]), 0.0, 0.0, 0, 0.0, 1.0)

    goal_lat, goal_lon = risk_map.idx_to_coord(*goal_idx)
    max_speed_ms = vessel.max_speed_knots * 0.5144

    def heuristic(node_idx):
        # Admissible: edge weights are >= travel time at max speed.
        lat, lon = risk_map.idx_to_coord(*node_idx)
        return haversine_distance(lat, lon, goal_lat, goal_lon) * 1000 / max_speed_ms

    # g = risk-weighted cost; elapsed time is tracked separately for time-dependent lookups.
    best_g = {start_idx: 0.0}
    elapsed = {start_idx: 0.0}
    parent: Dict[Tuple[int, int], Optional[Tuple[int, int]]] = {start_idx: None}
    closed = set()
    pq = [(heuristic(start_idx), 0.0, start_idx)]

    while pq:
        _, g, curr_idx = heapq.heappop(pq)
        if curr_idx in closed:
            continue
        closed.add(curr_idx)

        if curr_idx == goal_idx:
            break

        current_time_sec = elapsed[curr_idx]
        current_dt = departure_time + timedelta(seconds=current_time_sec)
        curr_coords = risk_map.idx_to_coord(*curr_idx)

        for nxt_idx in grid.get_neighbors(*curr_idx):
            if nxt_idx in closed:
                continue
            cost = risk_map.get_cost_by_idx(nxt_idx[0], nxt_idx[1], current_dt)
            if cost == np.inf:
                continue

            sic, thickness = _ice_at(grid, nxt_idx, current_dt)
            eff_speed = compute_effective_speed(vessel, sic, ice_thickness_m=thickness)
            if eff_speed <= 0:
                continue

            nxt_coords = risk_map.idx_to_coord(*nxt_idx)
            travel_time_sec = haversine_distance(*curr_coords, *nxt_coords) * 1000 / eff_speed
            new_g = g + travel_time_sec * (1.0 + risk_aversion * cost)

            if new_g < best_g.get(nxt_idx, float('inf')):
                best_g[nxt_idx] = new_g
                elapsed[nxt_idx] = current_time_sec + travel_time_sec
                parent[nxt_idx] = curr_idx
                heapq.heappush(pq, (new_g + heuristic(nxt_idx), new_g, nxt_idx))
    else:
        raise RouteNotFoundError(f"No safe passage found between points. A completely frozen ice sheet or landmass blocks the path for vessel class {vessel.name}.")

    cells = []
    node = goal_idx
    while node is not None:
        cells.append(node)
        node = parent[node]
    cells.reverse()

    arrival_times = [departure_time + timedelta(seconds=elapsed[c]) for c in cells]
    waypts = [risk_map.idx_to_coord(*c) for c in cells]
    # Report the user's actual endpoints rather than the snapped grid-cell centres.
    waypts[0], waypts[-1] = start, goal
    dist_km = sum(haversine_distance(*waypts[i], *waypts[i + 1]) for i in range(len(waypts) - 1))
    metrics = compute_route_metrics(grid, vessel, cells, arrival_times)

    return RouteResult(
        path=waypts,
        arrival_times=arrival_times,
        total_time_hours=elapsed[goal_idx] / 3600.0,
        total_distance_km=dist_km,
        **metrics,
    )

def time_dependent_astar(grid: RoutingGrid, vessel: VesselProfile, start: Tuple[float, float], goal: Tuple[float, float],
                         departure_time: datetime, risk_aversion: float = DEFAULT_RISK_AVERSION) -> Optional[RouteResult]:
    """Like find_route, but returns None instead of raising when no route exists."""
    try:
        return find_route(grid, vessel, start, goal, departure_time, risk_aversion)
    except RouteNotFoundError:
        return None
