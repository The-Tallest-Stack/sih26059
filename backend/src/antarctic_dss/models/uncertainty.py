import json
from pathlib import Path
import numpy as np
import pandas as pd

class UncertaintyEstimator:
    """
    Estimation of prediction uncertainty.
    """
    def __init__(self):
        self.a = 0.5  # default growth rate km/hour
        self.b = 1.0  # default base uncertainty km
        
    def calibrate(self, validation_df: pd.DataFrame, predicted_dx: np.ndarray, predicted_dy: np.ndarray) -> None:
        """
        Calibrate the uncertainty model using linear regression on validation errors.
        """
        target_dx = validation_df['target_dx'].values
        target_dy = validation_df['target_dy'].values
        horizons = validation_df.get('horizon_hours', pd.Series([24]*len(validation_df))).values
        
        errors_m = np.sqrt((predicted_dx - target_dx)**2 + (predicted_dy - target_dy)**2)
        errors_km = errors_m / 1000.0
        
        # Simple linear fit: error_km = a * horizon + b
        A = np.vstack([horizons, np.ones(len(horizons))]).T
        self.a, self.b = np.linalg.lstsq(A, errors_km, rcond=None)[0]
        
    def estimate(self, horizon_hours: int, seaice_concentration: float = 0.0) -> float:
        """
        Estimate uncertainty radius for a given horizon and sea ice concentration.
        """
        base_unc = self.a * horizon_hours + self.b
        return base_unc * (1.0 + seaice_concentration)
        
    def save(self, path: Path) -> None:
        """
        Save calibration parameters to JSON.
        """
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, 'w') as f:
            json.dump({'a': self.a, 'b': self.b}, f)
            
    def load(self, path: Path) -> None:
        """
        Load calibration parameters from JSON.
        """
        with open(path, 'r') as f:
            params = json.load(f)
            self.a = params['a']
            self.b = params['b']
