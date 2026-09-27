import pytest
from datetime import datetime, timedelta
from antarctic_dss.routing.departure import classify_risk, compute_confidence, DepartureOption
from antarctic_dss.routing.astar import RouteResult

def test_classify_risk_low():
    assert classify_risk(0.1) == 'Low'

def test_classify_risk_medium():
    assert classify_risk(0.5) == 'Medium'

def test_classify_risk_high():
    assert classify_risk(0.9) == 'High'

def test_confidence_degrades():
    route = RouteResult(
        path=[], arrival_times=[], total_time_hours=10, 
        total_distance_km=100, max_ice_exposure=0, avg_ice_exposure=0, 
        iceberg_proximity_events=0, route_risk_score=0.1, confidence=0.9
    )
    
    now = datetime.utcnow()
    conf_24h = compute_confidence(now + timedelta(hours=24), route)
    conf_72h = compute_confidence(now + timedelta(hours=72), route)
    
    assert conf_72h < conf_24h
