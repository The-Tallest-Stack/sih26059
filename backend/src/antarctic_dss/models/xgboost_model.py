import json
from pathlib import Path
from typing import Dict, Tuple, Optional
import numpy as np
import pandas as pd
from xgboost import XGBRegressor

# Targets are east/north iceberg displacement in metres per 24 h. Every feature must be
# available at inference time for a live USNIC iceberg: no drift history (lag) features, and
# no BYU 'disp' column (that is the observed displacement itself, i.e. target leakage).
FEATURE_COLS = [
    'lat', 'lon', 'size_km2', 'wind_u', 'wind_v',
    'ocean_current_u', 'ocean_current_v', 'seaice_drift_u', 'seaice_drift_v',
    'seaice_concentration', 'month_sin', 'month_cos',
    'physics_pred_dx', 'physics_pred_dy'
]

EARLY_STOPPING_ROUNDS = 50

XGB_DEFAULT_PARAMS = dict(
    n_estimators=500, max_depth=7, learning_rate=0.03, subsample=0.8,
    colsample_bytree=0.8, min_child_weight=5, reg_alpha=0.1, reg_lambda=1.0,
    # Pseudo-Huber loss (quadratic within ~2 km, linear beyond): daily displacements have
    # heavy-tailed noise from position fixes, and squared error let outliers dominate.
    # Chosen on validation error (5.63 -> 5.39 km on the 2023 split).
    objective='reg:pseudohubererror', huber_slope=2000.0,
    random_state=42, n_jobs=-1
)

class IcebergDisplacementModel:
    """
    XGBoost model for predicting iceberg displacement (dx, dy).
    """
    def __init__(self, params: Optional[Dict] = None):
        if params is None:
            params = XGB_DEFAULT_PARAMS
        self.model_dx = XGBRegressor(**params)
        self.model_dy = XGBRegressor(**params)
        
    def train(self, train_df: pd.DataFrame, val_df: Optional[pd.DataFrame] = None) -> None:
        """
        Train the XGBoost models.
        """
        X_train = train_df[FEATURE_COLS].fillna(0)
        y_train_dx = train_df['target_dx']
        y_train_dy = train_df['target_dy']
        
        eval_set_dx = None
        eval_set_dy = None
        
        if val_df is not None:
            X_val = val_df[FEATURE_COLS].fillna(0)
            y_val_dx = val_df['target_dx']
            y_val_dy = val_df['target_dy']
            eval_set_dx = [(X_val, y_val_dx)]
            eval_set_dy = [(X_val, y_val_dy)]
            
            # xgboost >= 2 takes early stopping as an estimator parameter, not a fit() argument.
            for model, eval_set, y in ((self.model_dx, eval_set_dx, y_train_dx), (self.model_dy, eval_set_dy, y_train_dy)):
                model.set_params(early_stopping_rounds=EARLY_STOPPING_ROUNDS)
                model.fit(X_train, y, eval_set=eval_set, verbose=False)
        else:
            for model, y in ((self.model_dx, y_train_dx), (self.model_dy, y_train_dy)):
                model.set_params(early_stopping_rounds=None)
                model.fit(X_train, y)
            
    def predict(self, df: pd.DataFrame) -> Tuple[np.ndarray, np.ndarray]:
        """
        Predict dx and dy arrays for given DataFrame.
        """
        X = df[FEATURE_COLS].fillna(0)
        dx_pred = self.model_dx.predict(X)
        dy_pred = self.model_dy.predict(X)
        return dx_pred, dy_pred
        
    def predict_single(self, features: Dict) -> Tuple[float, float]:
        """
        Predict for a single observation.
        """
        df = pd.DataFrame([features])
        dx, dy = self.predict(df)
        return float(dx[0]), float(dy[0])
        
    def evaluate(self, df: pd.DataFrame) -> Dict:
        """
        Evaluate predictions against targets.
        """
        dx_pred, dy_pred = self.predict(df)
        
        target_dx = df['target_dx'].values
        target_dy = df['target_dy'].values
        
        err_dx = dx_pred - target_dx
        err_dy = dy_pred - target_dy
        
        rmse_dx = float(np.sqrt(np.mean(err_dx**2)))
        rmse_dy = float(np.sqrt(np.mean(err_dy**2)))
        
        dist_err = np.sqrt(err_dx**2 + err_dy**2)
        rmse_total = float(np.sqrt(np.mean(dist_err**2)))
        mae_total = float(np.mean(dist_err))
        mean_position_error_km = float(mae_total / 1000.0)
        
        # R2 score calculation
        ss_res_dx = np.sum(err_dx**2)
        ss_tot_dx = np.sum((target_dx - np.mean(target_dx))**2)
        r2_dx = float(1 - (ss_res_dx / ss_tot_dx)) if ss_tot_dx > 0 else 0.0
        
        ss_res_dy = np.sum(err_dy**2)
        ss_tot_dy = np.sum((target_dy - np.mean(target_dy))**2)
        r2_dy = float(1 - (ss_res_dy / ss_tot_dy)) if ss_tot_dy > 0 else 0.0
        
        return {
            'rmse_dx': rmse_dx,
            'rmse_dy': rmse_dy,
            'rmse_total': rmse_total,
            'mae_total': mae_total,
            'mean_position_error_km': mean_position_error_km,
            'r2_dx': r2_dx,
            'r2_dy': r2_dy
        }
        
    def feature_importance(self) -> pd.DataFrame:
        """
        Return combined feature importance.
        """
        imp_dx = self.model_dx.feature_importances_
        imp_dy = self.model_dy.feature_importances_
        imp_mean = (imp_dx + imp_dy) / 2.0
        
        df = pd.DataFrame({
            'feature': FEATURE_COLS,
            'importance_dx': imp_dx,
            'importance_dy': imp_dy,
            'importance_mean': imp_mean
        })
        
        return df.sort_values(by='importance_mean', ascending=False).reset_index(drop=True)
        
    def save(self, model_dir: Path) -> None:
        """
        Save models to JSON.
        """
        model_dir.mkdir(parents=True, exist_ok=True)
        self.model_dx.save_model(model_dir / 'model_dx.json')
        self.model_dy.save_model(model_dir / 'model_dy.json')
        
    def load(self, model_dir: Path) -> None:
        """
        Load models from JSON.
        """
        self.model_dx.load_model(model_dir / 'model_dx.json')
        self.model_dy.load_model(model_dir / 'model_dy.json')
