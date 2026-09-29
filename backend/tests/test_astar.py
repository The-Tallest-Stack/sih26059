import pytest
import numpy as np
from datetime import datetime
from antarctic_dss.routing.astar import RoutingGrid, time_dependent_astar, RouteResult
from antarctic_dss.routing.risk_map import TimeDependentRiskMap, RiskMapConfig
from antarctic_dss.routing.vessel import DEFAULT_VESSELS

@pytest.fixture
def basic_grid():
    config = RiskMapConfig(lat_min=-60.0, lat_max=-59.0, lon_min=0.0, lon_max=1.0, resolution_deg=0.1)
    risk_map = TimeDependentRiskMap(config=config)
    time = datetime(2025, 1, 1)
    grid_data = np.zeros((risk_map.n_lat, risk_map.n_lon))
    risk_map.cost_grids[time] = grid_data
    return RoutingGrid(risk_map=risk_map)

def test_astar_simple_path(basic_grid):
    vessel = DEFAULT_VESSELS['icebreaker_pc5']
    start = (-60.0, 0.0)
    goal = (-59.0, 1.0)
    dt = datetime(2025, 1, 1)
    result = time_dependent_astar(basic_grid, vessel, start, goal, dt)
    assert result is not None
    assert len(result.path) > 1
    assert result.path[0] == start

def test_astar_blocked_path(basic_grid):
    # Block the grid
    time = datetime(2025, 1, 1)
    basic_grid.risk_map.cost_grids[time][:] = np.inf
    
    vessel = DEFAULT_VESSELS['icebreaker_pc5']
    start = (-60.0, 0.0)
    goal = (-59.0, 1.0)
    dt = datetime(2025, 1, 1)
    result = time_dependent_astar(basic_grid, vessel, start, goal, dt)
    assert result is None

def test_route_result_metrics(basic_grid):
    vessel = DEFAULT_VESSELS['icebreaker_pc5']
    start = (-60.0, 0.0)
    goal = (-59.9, 0.1)
    dt = datetime(2025, 1, 1)
    result = time_dependent_astar(basic_grid, vessel, start, goal, dt)
    
    assert isinstance(result, RouteResult)
    assert hasattr(result, 'total_time_hours')
    assert hasattr(result, 'total_distance_km')
    assert hasattr(result, 'max_ice_exposure')

def _built_grid(config, env_data, icebergs, vessel, time=datetime(2025, 1, 1)):
    risk_map = TimeDependentRiskMap(config=config)
    risk_map.build_time_slice(time, env_data, icebergs, vessel)
    return RoutingGrid(risk_map=risk_map)

def test_astar_detours_around_iceberg():
    from antarctic_dss.utils.geo import haversine_distance
    vessel = DEFAULT_VESSELS['icebreaker_pc5']
    config = RiskMapConfig(lat_min=-64.0, lat_max=-60.0, lon_min=0.0, lon_max=10.0, resolution_deg=0.25)
    iceberg = (-62.0, 5.0)
    grid = _built_grid(config, {}, [iceberg], vessel)

    result = time_dependent_astar(grid, vessel, (-62.0, 0.5), (-62.0, 9.5), datetime(2025, 1, 1))

    assert result is not None
    closest_km = min(haversine_distance(lat, lon, *iceberg) for lat, lon in result.path)
    assert closest_km >= 60.0
    assert result.iceberg_proximity_events == 0

def test_astar_crosses_antimeridian():
    vessel = DEFAULT_VESSELS['icebreaker_pc5']
    config = RiskMapConfig(lat_min=-66.0, lat_max=-64.0, lon_min=-180.0, lon_max=180.0, resolution_deg=0.5)
    grid = _built_grid(config, {}, [], vessel)

    result = time_dependent_astar(grid, vessel, (-65.0, 178.0), (-65.0, -178.0), datetime(2025, 1, 1))

    assert result is not None
    # ~4 degrees of longitude at 65S is ~190 km; going the long way round would be ~16,000 km.
    assert result.total_distance_km < 400
    assert all(abs(lon) >= 177.5 for _, lon in result.path)

def test_route_metrics_reflect_sea_ice():
    vessel = DEFAULT_VESSELS['icebreaker_pc5']
    config = RiskMapConfig(lat_min=-61.0, lat_max=-60.0, lon_min=0.0, lon_max=2.0, resolution_deg=0.1)
    risk_map = TimeDependentRiskMap(config=config)
    sic = np.full((risk_map.n_lat, risk_map.n_lon), 0.5)
    grid = _built_grid(config, {'real_sic': sic}, [], vessel)

    result = time_dependent_astar(grid, vessel, (-60.5, 0.0), (-60.5, 2.0), datetime(2025, 1, 1))

    assert result.max_ice_exposure == pytest.approx(0.5)
    assert result.avg_ice_exposure == pytest.approx(0.5)
    assert result.route_risk_score > 0
    assert result.arrival_times[-1] > result.arrival_times[0]
    # Sea ice slows the vessel: slower than open-water transit at max speed.
    open_water_hours = result.total_distance_km / (vessel.max_speed_knots * 1.852)
    assert result.total_time_hours > open_water_hours * 1.2
