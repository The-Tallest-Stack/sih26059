"""API tests that run offline: USNIC, the forecast cache, bathymetry and the drift model are stubbed."""
from datetime import datetime
from pathlib import Path

import geopandas as gpd
import pytest
from fastapi.testclient import TestClient
from shapely.geometry import Point

from antarctic_dss.api import routes_data, routes_voyage
from antarctic_dss.api.app import app

def fake_icebergs():
    return gpd.GeoDataFrame({
        'Iceberg': ['T1', 'T2'],
        'Length (NM)': [10, 5],
        'Width (NM)': [5, 3],
        'Last Update': ['09/24/2026', '09/24/2026'],
    }, geometry=[Point(-35.0, -60.0), Point(-100.0, -70.0)], crs='EPSG:4326')

@pytest.fixture
def client(monkeypatch):
    import antarctic_dss.data.usnic_live as usnic
    import antarctic_dss.routing.bathymetry as bathymetry
    monkeypatch.setattr(usnic, 'fetch_current_icebergs', lambda *a, **k: fake_icebergs())
    missing = Path('does-not-exist.zarr')
    monkeypatch.setattr(routes_voyage, 'FORECAST_ZARR', missing)
    monkeypatch.setattr(routes_data, 'FORECAST_ZARR', missing)
    monkeypatch.setattr(bathymetry, 'depth_on_grid', lambda *a, **k: None)
    monkeypatch.setattr(routes_data, 'drift_model_beats_persistence', lambda: False)
    return TestClient(app)

def plan(client, a, b, start='2026-10-01T00:00:00Z', end='2026-10-01T12:00:00Z', vessel='icebreaker_pc5'):
    return client.post('/api/voyage/plan', json={
        'point_a': {'lat': a[0], 'lon': a[1]}, 'point_b': {'lat': b[0], 'lon': b[1]},
        'vessel_id': vessel, 'window_start': start, 'window_end': end})

def test_vessels(client):
    r = client.get('/api/vessels')
    assert r.status_code == 200
    vessels = {v['id']: v for v in r.json()}
    assert {'icebreaker_pc1', 'icebreaker_pc2', 'icebreaker_pc3', 'icebreaker_pc4', 'icebreaker_pc5',
            'research_vessel', 'supply_vessel'} <= set(vessels)
    assert vessels['icebreaker_pc1']['max_ice_thickness_m'] > vessels['icebreaker_pc5']['max_ice_thickness_m']

def test_freshness_without_forecast_cache(client):
    sources = {s['source']: s for s in client.get('/api/data/freshness').json()}
    assert sources['USNIC Icebergs']['last_updated'].startswith('2026-09-24')
    for name in ('Copernicus Sea Ice Forecast', 'Copernicus Ocean Currents', 'Wind Forecast'):
        assert sources[name]['status'] == 'unavailable'
        assert sources[name]['last_updated'] is None

def test_plan_voyage_open_water(client):
    r = plan(client, (-60.0, -45.0), (-60.0, -25.0))
    assert r.status_code == 200
    body = r.json()
    assert body['status'] == 'completed'
    assert body['comparison_summary']['iceberg_positions'] == 'current'
    options = body['options']
    assert len(options) >= 2  # 12 h window, 6 h interval
    risks = [o['route_geojson']['features'][0]['properties']['risk'] for o in options]
    assert risks == sorted(risks)  # best (lowest risk) first
    coords = options[0]['route_geojson']['features'][0]['geometry']['coordinates']
    assert coords[0] == [-45.0, -60.0] and coords[-1] == [-25.0, -60.0]
    # The route must keep clear of iceberg T1 at (-60, -35), which sits on the direct line.
    from antarctic_dss.utils.geo import haversine_distance
    assert min(haversine_distance(lat, lon, -60.0, -35.0) for lon, lat in coords) >= 55.0
    assert options[0]['icebergs_avoided'] == 1

def test_plan_rejects_inverted_window(client):
    r = plan(client, (-60.0, -45.0), (-60.0, -25.0), start='2026-10-02T00:00:00Z', end='2026-10-01T00:00:00Z')
    assert r.status_code == 422

def test_sea_ice_requires_cache(client):
    assert client.get('/api/environment/seaice').status_code == 503

def test_risk_map_unknown_vessel(client):
    assert client.get('/api/environment/risk-map?vessel_id=nope').status_code == 404

def test_trajectory_unknown_iceberg(client):
    assert client.get('/api/icebergs/NOPE/trajectory').status_code == 404

def test_risk_map_accepts_time_varying_iceberg_positions():
    from antarctic_dss.routing.risk_map import TimeDependentRiskMap, RiskMapConfig
    from antarctic_dss.routing.vessel import DEFAULT_VESSELS

    risk_map = TimeDependentRiskMap(RiskMapConfig(lat_min=-62, lat_max=-58, lon_min=-50, lon_max=-20, resolution_deg=0.5))
    start = datetime(2026, 10, 1)

    def moving(t):  # drifts 1 degree east every 6 h
        return [(-60.0, -40.0 + (t - start).total_seconds() / 21600.0, 0.0)]

    risk_map.build_all_slices(start, 6, {}, moving, DEFAULT_VESSELS['icebreaker_pc5'])
    first, second = (risk_map.env_slices[t].iceberg_count for t in sorted(risk_map.env_slices))
    i, j0 = risk_map.coord_to_idx(-60.0, -40.0)
    _, j1 = risk_map.coord_to_idx(-60.0, -39.0)
    assert first[i, j0] == 1 and second[i, j1] == 1
    assert (first != second).any()

def test_route_does_not_cross_small_island(client):
    """A ~0.17 degree island (smaller than a 0.5 degree routing cell) sits between the points."""
    from shapely.geometry import LineString
    from antarctic_dss.api.routes_voyage import _land_geometries
    r = plan(client, (-60.6, -54.1), (-61.9, -54.1), vessel='icebreaker_pc1')
    assert r.status_code == 200 and r.json()['status'] == 'completed'
    coords = r.json()['options'][0]['route_geojson']['features'][0]['geometry']['coordinates']
    # Skip the first/last legs: they join the user's exact points to the grid.
    route = LineString(coords[1:-1])
    assert not _land_geometries().intersects(route).any()

def test_heavier_polar_classes_handle_thicker_ice():
    from antarctic_dss.routing.risk_map import TimeDependentRiskMap
    from antarctic_dss.routing.vessel import DEFAULT_VESSELS, compute_effective_speed
    risk_map = TimeDependentRiskMap()
    cost = lambda vid, thick: risk_map.compute_cell_cost(0.9, 0.0, 0.0, 0.0, 1000.0, DEFAULT_VESSELS[vid], ice_thickness=thick)
    assert cost('icebreaker_pc5', 2.0) == float('inf')      # 2 m ice: beyond PC5
    assert cost('icebreaker_pc3', 2.0) < float('inf')       # within PC3
    assert cost('icebreaker_pc1', 3.5) < float('inf')       # multi-year ice: PC1 only
    assert cost('icebreaker_pc2', 3.5) == float('inf')
    pc1 = DEFAULT_VESSELS['icebreaker_pc1']
    assert compute_effective_speed(pc1, 0.9, ice_thickness_m=3.0) < compute_effective_speed(pc1, 0.9, ice_thickness_m=0.5)
