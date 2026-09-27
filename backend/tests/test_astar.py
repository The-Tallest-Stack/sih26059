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
