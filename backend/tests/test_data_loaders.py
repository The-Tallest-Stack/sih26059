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
