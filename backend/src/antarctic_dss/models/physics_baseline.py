import numpy as np
import pandas as pd
from typing import Tuple

def free_drift_displacement(
    wind_u: float, wind_v: float, 
    current_u: float, current_v: float, 
    seaice_drift_u: float, seaice_drift_v: float, 
    seaice_concentration: float, 
    dt_seconds: float = 86400.0, 
    wind_factor: float = 0.025, 
    coriolis_angle_deg: float = -25.0, 
    ice_lock_threshold: float = 0.8
) -> Tuple[float, float]:
    """
    This implements the classical free-drift model. Icebergs drift under wind and ocean current forcing: v_iceberg ≈ v_current + α · R(θ) · v_wind, where α ≈ 0.02-0.04 and θ ≈ -25° (Southern Hemisphere Coriolis deflection). When sea ice concentration exceeds a threshold, the iceberg is locked to sea-ice drift.
    
    Args:
        wind_u: u-component of wind velocity (m/s)
        wind_v: v-component of wind velocity (m/s)
        current_u: u-component of ocean current velocity (m/s)
        current_v: v-component of ocean current velocity (m/s)
        seaice_drift_u: u-component of sea ice drift velocity (m/s)
        seaice_drift_v: v-component of sea ice drift velocity (m/s)
        seaice_concentration: Sea ice concentration fraction (0 to 1)
        dt_seconds: Time step in seconds (default 86400.0)
        wind_factor: Wind scaling factor (alpha)
        coriolis_angle_deg: Rotation angle in degrees
        ice_lock_threshold: Threshold above which iceberg follows sea ice
        
    Returns:
        Tuple of (dx, dy) in meters.
    """
    if seaice_concentration >= ice_lock_threshold:
        return (seaice_drift_u * dt_seconds, seaice_drift_v * dt_seconds)
    
    theta_rad = np.radians(coriolis_angle_deg)
    cos_theta = np.cos(theta_rad)
    sin_theta = np.sin(theta_rad)
    
    # R(theta) * v_wind
    wind_rot_u = wind_u * cos_theta - wind_v * sin_theta
    wind_rot_v = wind_u * sin_theta + wind_v * cos_theta
    
    v_iceberg_u = current_u + wind_factor * wind_rot_u
    v_iceberg_v = current_v + wind_factor * wind_rot_v
    
    dx = v_iceberg_u * dt_seconds
    dy = v_iceberg_v * dt_seconds
    
    return float(dx), float(dy)

def batch_free_drift(df: pd.DataFrame, dt_seconds: float = 86400.0) -> pd.DataFrame:
    """
    Apply free_drift_displacement to each row of a DataFrame using vectorized operations.
    
    Args:
        df: DataFrame with forcing variables.
        dt_seconds: Time step in seconds.
        
    Returns:
        DataFrame with added 'physics_pred_dx' and 'physics_pred_dy' columns.
    """
    wind_factor = 0.025
    theta_rad = np.radians(-25.0)
    cos_theta = np.cos(theta_rad)
    sin_theta = np.sin(theta_rad)
    ice_lock_threshold = 0.8
    
    locked_mask = df['seaice_concentration'] >= ice_lock_threshold
    
    wind_rot_u = df['wind_u'] * cos_theta - df['wind_v'] * sin_theta
    wind_rot_v = df['wind_u'] * sin_theta + df['wind_v'] * cos_theta
    
    v_iceberg_u = df['ocean_current_u'] + wind_factor * wind_rot_u
    v_iceberg_v = df['ocean_current_v'] + wind_factor * wind_rot_v
    
    dx_free = v_iceberg_u * dt_seconds
    dy_free = v_iceberg_v * dt_seconds
    
    dx_locked = df['seaice_drift_u'] * dt_seconds
    dy_locked = df['seaice_drift_v'] * dt_seconds
    
    physics_pred_dx = np.where(locked_mask, dx_locked, dx_free)
    physics_pred_dy = np.where(locked_mask, dy_locked, dy_free)
    
    df = df.copy()
    df['physics_pred_dx'] = physics_pred_dx
    df['physics_pred_dy'] = physics_pred_dy
    
    return df

def evaluate_physics_baseline(df: pd.DataFrame) -> dict:
    """
    Compare physics_pred_dx/dy against target_dx/dy.
    
    Args:
        df: DataFrame containing predictions and targets.
        
    Returns:
        Dict with evaluation metrics.
    """
    err_dx = df['physics_pred_dx'] - df['target_dx']
    err_dy = df['physics_pred_dy'] - df['target_dy']
    
    rmse_dx = np.sqrt(np.mean(err_dx**2))
    rmse_dy = np.sqrt(np.mean(err_dy**2))
    
    dist_err = np.sqrt(err_dx**2 + err_dy**2)
    rmse_total = np.sqrt(np.mean(dist_err**2))
    mae_total = np.mean(dist_err)
    mean_position_error_km = mae_total / 1000.0
    
    return {
        'rmse_dx': rmse_dx,
        'rmse_dy': rmse_dy,
        'rmse_total': rmse_total,
        'mae_total': mae_total,
        'mean_position_error_km': mean_position_error_km
    }
