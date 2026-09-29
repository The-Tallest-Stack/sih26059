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
    # Thickest level ice (m) the vessel can operate in (IACS Polar Class guidance).
    max_ice_thickness_m: float = float('inf')

DEFAULT_VESSELS = {
    'icebreaker_pc1': VesselProfile(
        name='Polar Class 1 Heavy Icebreaker',
        max_speed_knots=18.0,
        max_ice_concentration=1.0,
        ice_speed_factor=0.5,
        draft_m=11.0,
        ice_class='PC1',
        description='Year-round operation in all polar waters, including thick multi-year ice',
        max_ice_thickness_m=4.0,
    ),
    'icebreaker_pc2': VesselProfile(
        name='Polar Class 2 Icebreaker',
        max_speed_knots=17.0,
        max_ice_concentration=1.0,
        ice_speed_factor=0.55,
        draft_m=10.5,
        ice_class='PC2',
        description='Year-round operation in moderate multi-year ice',
        max_ice_thickness_m=3.0,
    ),
    'icebreaker_pc3': VesselProfile(
        name='Polar Class 3 Icebreaker',
        max_speed_knots=16.0,
        max_ice_concentration=1.0,
        ice_speed_factor=0.6,
        draft_m=9.5,
        ice_class='PC3',
        description='Year-round operation in second-year ice with multi-year inclusions',
        max_ice_thickness_m=2.5,
    ),
    'icebreaker_pc4': VesselProfile(
        name='Polar Class 4 Icebreaker',
        max_speed_knots=15.0,
        max_ice_concentration=0.9,
        ice_speed_factor=0.6,
        draft_m=9.0,
        ice_class='PC4',
        description='Year-round operation in thick first-year ice with old ice inclusions',
        max_ice_thickness_m=1.5,
    ),
    'icebreaker_pc5': VesselProfile(
        name='Polar Class 5 Icebreaker',
        max_speed_knots=15.0,
        max_ice_concentration=0.8,
        ice_speed_factor=0.6,
        draft_m=8.0,
        ice_class='PC5',
        description='Year-round operation in medium first-year ice with old ice inclusions',
        max_ice_thickness_m=1.2,
    ),
    'research_vessel': VesselProfile(
        name='Research Vessel (Ice Class 1A)',
        max_speed_knots=12.0,
        max_ice_concentration=0.5,
        ice_speed_factor=0.4,
        draft_m=6.5,
        ice_class='1A',
        description='Ice-strengthened research vessel for seasonal Antarctic operations',
        max_ice_thickness_m=0.8,
    ),
    'supply_vessel': VesselProfile(
        name='Supply Vessel (No Ice Class)',
        max_speed_knots=14.0,
        max_ice_concentration=0.15,
        ice_speed_factor=0.1,
        draft_m=5.0,
        ice_class='none',
        description='Standard supply vessel restricted to open water and light ice',
        max_ice_thickness_m=0.3,
    )
}

def compute_effective_speed(vessel: VesselProfile, sic: float, current_u: float = 0, current_v: float = 0,
                            heading_deg: float = 0, ice_thickness_m: float = 0.0) -> float:
    """
    Computes effective speed in m/s considering sea ice concentration, thickness and currents.

    In ice (> 15% cover) speed falls with concentration, and further with thickness relative
    to the vessel's rated thickness (down to 20% of the ice-concentration speed at its limit).
    """
    if sic > vessel.max_ice_concentration:
        return 0.0
    if sic > 0.15 and ice_thickness_m > vessel.max_ice_thickness_m:
        return 0.0

    base_speed_ms = vessel.max_speed_knots * 0.5144
    speed = base_speed_ms

    if sic > 0.15:
        speed *= max(0.0, 1.0 - sic * vessel.ice_speed_factor)
        if ice_thickness_m > 0 and np.isfinite(vessel.max_ice_thickness_m):
            speed *= max(0.2, 1.0 - 0.8 * min(1.0, ice_thickness_m / vessel.max_ice_thickness_m))

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
