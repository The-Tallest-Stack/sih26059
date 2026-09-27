import pytest
from antarctic_dss.models.physics_baseline import free_drift_displacement

def test_free_drift_open_water():
    # zero ice, some wind and current
    dx, dy = free_drift_displacement(
        wind_u=10.0, wind_v=0.0,
        current_u=0.5, current_v=0.0,
        seaice_drift_u=0.0, seaice_drift_v=0.0,
        seaice_concentration=0.0,
        dt_seconds=3600.0,
        wind_factor=0.025,
        coriolis_angle_deg=0.0 # Simplify angle
    )
    # expected dx = (0.5 + 0.025 * 10) * 3600 = (0.5 + 0.25) * 3600 = 0.75 * 3600 = 2700.0
    assert pytest.approx(dx) == 2700.0
    assert pytest.approx(dy) == 0.0

def test_free_drift_locked_in_ice():
    # high ice concentration
    dx, dy = free_drift_displacement(
        wind_u=10.0, wind_v=0.0,
        current_u=0.5, current_v=0.0,
        seaice_drift_u=0.2, seaice_drift_v=0.1,
        seaice_concentration=0.9,
        dt_seconds=3600.0
    )
    # Should equal seaice drift * dt
    assert pytest.approx(dx) == 0.2 * 3600.0
    assert pytest.approx(dy) == 0.1 * 3600.0

def test_free_drift_zero_forcing():
    dx, dy = free_drift_displacement(
        wind_u=0.0, wind_v=0.0,
        current_u=0.0, current_v=0.0,
        seaice_drift_u=0.0, seaice_drift_v=0.0,
        seaice_concentration=0.0
    )
    assert dx == 0.0
    assert dy == 0.0

def test_coriolis_rotation():
    # Only wind in +x direction
    dx, dy = free_drift_displacement(
        wind_u=10.0, wind_v=0.0,
        current_u=0.0, current_v=0.0,
        seaice_drift_u=0.0, seaice_drift_v=0.0,
        seaice_concentration=0.0,
        coriolis_angle_deg=-25.0,
        dt_seconds=1.0
    )
    # With -25 deg rotation, v component should be negative (since sin(-25) is negative)
    assert dx > 0
    assert dy < 0
