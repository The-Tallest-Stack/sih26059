from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, List, Dict, Any

class CoordinateSchema(BaseModel):
    lat: float = Field(..., ge=-90, le=90, description='Latitude in decimal degrees')
    lon: float = Field(..., ge=-180, le=180, description='Longitude in decimal degrees')

class VesselProfileSchema(BaseModel):
    id: str
    name: str
    max_speed_knots: float
    max_ice_concentration: float
    ice_speed_factor: float
    draft_m: float
    ice_class: str
    description: str = ''

class VoyageRequest(BaseModel):
    point_a: CoordinateSchema
    point_b: CoordinateSchema
    vessel_id: str = Field(default='icebreaker_pc5', description='Vessel profile ID')
    window_start: datetime = Field(..., description='Start of departure window')
    window_end: datetime = Field(..., description='End of departure window')
    interval_hours: int = Field(default=6, ge=1, le=24, description='Hours between candidate departures')

class RouteSchema(BaseModel):
    path: List[CoordinateSchema]
    arrival_times: List[datetime]
    total_time_hours: float
    total_distance_km: float
    max_ice_exposure: float
    avg_ice_exposure: float
    iceberg_proximity_events: int
    route_risk_score: float
    confidence: float

class DepartureOptionSchema(BaseModel):
    departure_time: datetime
    risk_summary: str
    eta: datetime
    travel_time_hours: float
    distance_km: float
    max_ice_concentration_en_route: float
    iceberg_proximity_events: int
    prediction_confidence: float
    route_geojson: Dict[str, Any]  # GeoJSON FeatureCollection

class VoyageResultSchema(BaseModel):
    id: str
    status: str = 'completed'
    options: List[DepartureOptionSchema]
    icebergs_geojson: Dict[str, Any]  # GeoJSON FeatureCollection
    comparison_summary: Dict[str, Any]

class DataFreshnessSchema(BaseModel):
    source: str
    last_updated: datetime
    age_minutes: float
    status: str  # 'fresh', 'stale', 'unavailable'

class IcebergPositionSchema(BaseModel):
    iceberg_id: str
    lat: float
    lon: float
    length_nm: float
    width_nm: float
    area_km2: float
    last_update: str

class TrajectorySchema(BaseModel):
    iceberg_id: str
    points: List[Dict[str, Any]]  # [{time, lat, lon, uncertainty_km}]
    geojson: Dict[str, Any]

class ErrorResponse(BaseModel):
    detail: str
    error_code: str = 'UNKNOWN'
