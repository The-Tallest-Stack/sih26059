from datetime import datetime, timezone

import pytest

from antarctic_dss.models.trajectory import TrajectoryGenerator

class EastwardModel:
    """Stub model: 10 km/day due east, regardless of features."""
    def predict_single(self, features):
        return 10_000.0, 0.0

def calm_sampler(x, y, t):
    return {'wind_u': 0.0, 'wind_v': 0.0, 'ocean_current_u': 0.0, 'ocean_current_v': 0.0,
            'seaice_drift_u': 0.0, 'seaice_drift_v': 0.0, 'seaice_concentration': 0.0}

@pytest.mark.parametrize('lon', [0.0, 90.0, -120.0, 179.9])
def test_eastward_prediction_moves_east_at_any_longitude(lon):
    generator = TrajectoryGenerator(model=EastwardModel())
    state = {'iceberg_id': 'T1', 'time': datetime(2026, 1, 1, tzinfo=timezone.utc), 'lat': -58.0, 'lon': lon}

    traj = generator.predict_trajectory(state, calm_sampler, horizons_hours=[24])
    end = traj.points[-1]

    assert end.lat == pytest.approx(-58.0, abs=1e-3)
    # 10 km east at 58S is ~0.17 degrees of longitude (wrapping past 180 near the antimeridian).
    dlon = (end.lon - lon + 180) % 360 - 180
    assert dlon == pytest.approx(10.0 / (111.195 * 0.5299), rel=0.02)
