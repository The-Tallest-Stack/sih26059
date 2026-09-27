import pytest
import numpy as np
from datetime import datetime
from antarctic_dss.routing.risk_map import TimeDependentRiskMap, RiskMapConfig
from antarctic_dss.routing.vessel import DEFAULT_VESSELS

def test_impassable_high_ice():
    risk_map = TimeDependentRiskMap()
    vessel = DEFAULT_VESSELS['icebreaker_pc5']
    cost = risk_map.compute_cell_cost(sic=0.9, iceberg_risk=0.0, wind_speed=0.0, wave_height=0.0, depth_m=100.0, vessel=vessel)
    assert cost == np.inf

def test_open_water_low_cost():
    risk_map = TimeDependentRiskMap()
    vessel = DEFAULT_VESSELS['icebreaker_pc5']
    cost = risk_map.compute_cell_cost(sic=0.0, iceberg_risk=0.0, wind_speed=0.0, wave_height=0.0, depth_m=100.0, vessel=vessel)
    assert cost == 0.0

def test_iceberg_increases_cost():
    risk_map = TimeDependentRiskMap()
    vessel = DEFAULT_VESSELS['icebreaker_pc5']
    base_cost = risk_map.compute_cell_cost(sic=0.0, iceberg_risk=0.0, wind_speed=0.0, wave_height=0.0, depth_m=100.0, vessel=vessel)
    iceberg_cost = risk_map.compute_cell_cost(sic=0.0, iceberg_risk=0.5, wind_speed=0.0, wave_height=0.0, depth_m=100.0, vessel=vessel)
    assert iceberg_cost > base_cost

def test_grid_dimensions():
    config = RiskMapConfig(lat_min=-60.0, lat_max=-50.0, lon_min=0.0, lon_max=10.0, resolution_deg=1.0)
    risk_map = TimeDependentRiskMap(config=config)
    assert risk_map.n_lat == 11
    assert risk_map.n_lon == 11
