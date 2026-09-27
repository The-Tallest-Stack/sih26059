from dataclasses import dataclass, field
from typing import Optional
import numpy as np

@dataclass
class VesselProfile:
    """
    Profile representing a vessel's characteristics and capabilities in ice.
    """
    name: str
    max_speed_knots: float
    max_ice_concentration: float
    ice_speed_factor: float
    draft_m: float
    ice_class: str
    description: str = ''

DEFAULT_VESSELS = {
    'icebreaker_pc5': VesselProfile(
        name='Polar Class 5 Icebreaker',
        max_speed_knots=15.0,
        max_ice_concentration=0.8,
        ice_speed_factor=0.6,
        draft_m=8.0,
        ice_class='PC5',
        description='Heavy icebreaker capable of year-round Antarctic operations'
    ),
    'research_vessel': VesselProfile(
        name='Research Vessel (Ice Class 1A)',
        max_speed_knots=12.0,
        max_ice_concentration=0.5,
        ice_speed_factor=0.4,
        draft_m=6.5,
        ice_class='1A',
        description='Ice-strengthened research vessel for seasonal Antarctic operations'
    ),
    'supply_vessel': VesselProfile(
        name='Supply Vessel (No Ice Class)',
        max_speed_knots=14.0,
        max_ice_concentration=0.15,
        ice_speed_factor=0.1,
        draft_m=5.0,
        ice_class='none',
        description='Standard supply vessel restricted to open water and light ice'
    )
}

def compute_effective_speed(vessel: VesselProfile, sic: float, current_u: float = 0, current_v: float = 0, heading_deg: float = 0) -> float:
    """
    Computes effective speed in m/s considering sea ice concentration and currents.
    """
    if sic > vessel.max_ice_concentration:
        return 0.0
    
    base_speed_ms = vessel.max_speed_knots * 0.5144
    speed = base_speed_ms
    
    if sic > 0.15:
        speed *= max(0.0, 1.0 - sic * vessel.ice_speed_factor)
        
    heading_rad = np.radians(heading_deg)
    current_proj = current_u * np.sin(heading_rad) + current_v * np.cos(heading_rad)
    
    speed += current_proj
    return max(0.0, speed)

def estimate_transit_time(vessel: VesselProfile, distance_m: float, sic: float) -> float:
    """
    Estimates transit time in seconds over a given distance and sea ice concentration.
    Returns np.inf if impassable.
    """
    speed = compute_effective_speed(vessel, sic)
    if speed <= 0:
        return np.inf
    return distance_m / speed
