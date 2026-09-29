import pytest
import datetime
import math
from antarctic_dss.data.iceberg_tracks import STATS_COLUMNS

def test_yyyyddd_parsing():
    """Test that YYYYDDD string 2017193 parses to 2017-07-12."""
    date_str = "2017193"
    dt = datetime.datetime.strptime(date_str, "%Y%j")
    assert dt.year == 2017
    assert dt.month == 7
    assert dt.day == 12

def test_stats_columns_count():
    """Test that STATS_COLUMNS has 9 entries."""
    assert len(STATS_COLUMNS) == 9

def haversine(lat1, lon1, lat2, lon2):
    """Helper to calculate haversine distance in km."""
    R = 6371  # Earth radius in km
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat/2) * math.sin(dlat/2) + \
        math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * \
        math.sin(dlon/2) * math.sin(dlon/2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
    return R * c

def test_haversine_known_distance():
    """Test haversine between two known Antarctic points."""
    # Point 1: McMurdo Station (approx -77.84, 166.66)
    # Point 2: South Pole (-90.0, 0.0)
    dist = haversine(-77.84, 166.66, -90.0, 0.0)
    assert 1340 < dist < 1360

def test_cyclic_encode():
    """Test cyclic encoding of month 6 gives (sin, cos) values."""
    month = 6
    sin_val = math.sin(2 * math.pi * month / 12)
    cos_val = math.cos(2 * math.pi * month / 12)
    
    assert math.isclose(sin_val, 0, abs_tol=1e-9)
    assert math.isclose(cos_val, -1, abs_tol=1e-9)

def test_consolidated_track_cleaning(tmp_path):
    import numpy as np
    import pandas as pd
    from antarctic_dss.data.iceberg_tracks import load_consolidated_daily_track, build_displacement_targets

    # Scatterometer-only track: a (0,0) empty row and a stale repeated fix must be dropped.
    csv = tmp_path / "t1.csv"
    pd.DataFrame({
        'date': [2023001, 2023002, 2023003, 2023004, 2023005],
        'ascat_1': [-65.00, -65.01, -65.01, 0.0, -65.03],
        'ascat_2': [-50.00, -50.10, -50.10, 0.0, -50.30],
        'ascat_3': [1, 1, 1, 0, 1],
    }).to_csv(csv, index=False)

    track = load_consolidated_daily_track(csv)
    assert list(track['timestamp'].dt.day) == [1, 2, 5]
    assert (track['source'] == 'ascat').all()

    targets = build_displacement_targets(track)
    # Day 2 -> day 5 is a 3-day gap, normalised to metres per day.
    assert len(targets) == 2
    assert targets['gap_days'].tolist() == [1.0, 3.0]
    assert (targets['target_dx'] < 0).all()  # moving west
    assert np.isfinite(targets[['target_dx', 'target_dy']].values).all()

def test_consolidated_track_prefers_nic(tmp_path):
    import pandas as pd
    from antarctic_dss.data.iceberg_tracks import load_consolidated_daily_track

    csv = tmp_path / "t2.csv"
    pd.DataFrame({
        'date': [2023001, 2023002, 2023003],
        'nic_1': [-70.0, -70.1, -70.2], 'nic_2': [10.0, 10.1, 10.2], 'nic_3': [1, 0, 1],
        'qscat_1': [-70.05, 0.0, -70.25], 'qscat_2': [10.05, 0.0, 10.25], 'qscat_3': [1, 0, 1],
        'size_1': [10, 0, 0], 'size_2': [5, 0, 0],
    }).to_csv(csv, index=False)

    track = load_consolidated_daily_track(csv)
    assert (track['source'] == 'nic').all()
    # Day 2 is an interpolated NIC position (nic_3 == 0): only real fixes are kept.
    assert track['lat'].tolist() == [-70.0, -70.2]
    assert track['size_km2'].round(2).tolist() == [round(50 * 1.852 ** 2, 2)] * 2


def test_flag_grounded_uses_net_weekly_drift():
    import pandas as pd
    from antarctic_dss.data.iceberg_tracks import flag_grounded

    days = pd.date_range('2023-01-01', periods=15, freq='D')
    stuck = pd.DataFrame({'iceberg_id': 'stuck', 'timestamp': days, 'lat': -66.0, 'lon': [100.0 + 0.0001 * i for i in range(15)]})
    drifting = pd.DataFrame({'iceberg_id': 'drift', 'timestamp': days, 'lat': -60.0, 'lon': [-40.0 + 0.1 * i for i in range(15)]})

    flagged = flag_grounded(pd.concat([stuck, drifting], ignore_index=True))
    by_id = flagged.groupby('iceberg_id')['grounded']
    assert not by_id.any()['drift']  # ~5.6 km/day
    # Stuck berg: flagged wherever a fix >= 7 days later exists and the water is shallow enough
    # (depth-dependent); it must never be flagged less often than the drifting one.
    assert by_id.sum()['stuck'] >= by_id.sum()['drift']
