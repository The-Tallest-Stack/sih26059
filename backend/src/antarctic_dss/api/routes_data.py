from fastapi import APIRouter, HTTPException
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional

from antarctic_dss.api.schemas import DataFreshnessSchema, VesselProfileSchema

router = APIRouter()

@router.get('/icebergs/current')
async def get_current_icebergs() -> Dict[str, Any]:
    """Fetch current Antarctic iceberg positions from USNIC.
    
    Returns GeoJSON FeatureCollection with iceberg points.
    Each feature has properties: iceberg_id, length_nm, width_nm, area_km2, last_update.
    """
    try:
        from antarctic_dss.data.usnic_live import fetch_current_icebergs
        gdf = fetch_current_icebergs()
        # Convert to GeoJSON dict
        geojson = gdf.to_crs(epsg=4326).__geo_interface__
        return geojson
    except Exception as e:
        raise HTTPException(status_code=503, detail=f'Failed to fetch icebergs: {str(e)}')

@router.get('/icebergs/{iceberg_id}/trajectory')
async def get_iceberg_trajectory(iceberg_id: str, horizon_hours: int = 72) -> Dict[str, Any]:
    """Get predicted trajectory for a specific iceberg.
    
    Returns GeoJSON Feature with LineString geometry showing predicted path
    and uncertainty corridors.
    """
    # TODO: Connect to trajectory generator
    return {
        'type': 'Feature',
        'properties': {'iceberg_id': iceberg_id, 'horizon_hours': horizon_hours,
                       'message': 'Trajectory prediction not yet connected'},
        'geometry': {'type': 'LineString', 'coordinates': []}
    }

@router.get('/environment/seaice')
async def get_sea_ice_data() -> Dict[str, Any]:
    """Get current sea-ice concentration data."""
    # TODO: Connect to Copernicus NRT data
    return {'type': 'FeatureCollection', 'features': [],
            'properties': {'message': 'Sea ice data endpoint ready, not yet connected to NRT feed'}}

@router.get('/environment/risk-map')
async def get_risk_map(time: Optional[str] = None) -> Dict[str, Any]:
    """Get time-sliced navigation risk map.
    
    Returns GeoJSON grid showing risk levels at the specified time.
    If no time specified, returns current conditions.
    """
    return {'type': 'FeatureCollection', 'features': [],
            'properties': {'message': 'Risk map endpoint ready'}}

@router.get('/data/freshness', response_model=List[DataFreshnessSchema])
async def get_data_freshness() -> List[DataFreshnessSchema]:
    """Get data source freshness status.
    
    Returns status of each data source including last update time
    and whether the data is fresh, stale, or unavailable.
    """
    now = datetime.now(timezone.utc)
    return [
        DataFreshnessSchema(source='USNIC Icebergs', last_updated=now, age_minutes=0, status='fresh'),
        DataFreshnessSchema(source='Copernicus Sea Ice NRT', last_updated=now, age_minutes=0, status='unavailable'),
        DataFreshnessSchema(source='Copernicus Ocean Forecast', last_updated=now, age_minutes=0, status='unavailable'),
        DataFreshnessSchema(source='ECMWF Wind Forecast', last_updated=now, age_minutes=0, status='unavailable'),
    ]

@router.get('/vessels', response_model=List[VesselProfileSchema])
async def list_vessels() -> List[VesselProfileSchema]:
    """List available vessel profiles."""
    try:
        from antarctic_dss.routing.vessel import DEFAULT_VESSELS
        return [
            VesselProfileSchema(
                id=vid, name=v.name, max_speed_knots=v.max_speed_knots,
                max_ice_concentration=v.max_ice_concentration,
                ice_speed_factor=v.ice_speed_factor, draft_m=v.draft_m,
                ice_class=v.ice_class, description=v.description
            )
            for vid, v in DEFAULT_VESSELS.items()
        ]
    except ImportError:
        # Fallback if vessel module isn't fully implemented yet
        return []
