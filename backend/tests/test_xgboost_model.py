import pytest
import numpy as np
import pandas as pd
from pathlib import Path
from antarctic_dss.models.xgboost_model import IcebergDisplacementModel, FEATURE_COLS

@pytest.fixture
def synthetic_data():
    np.random.seed(42)
    n = 100
    df = pd.DataFrame(np.random.randn(n, len(FEATURE_COLS)), columns=FEATURE_COLS)
    df['target_dx'] = df['physics_pred_dx'] + np.random.randn(n) * 100
    df['target_dy'] = df['physics_pred_dy'] + np.random.randn(n) * 100
    return df

def test_model_train_predict(synthetic_data):
    model = IcebergDisplacementModel()
    model.train(synthetic_data)
    
    dx_pred, dy_pred = model.predict(synthetic_data)
    assert len(dx_pred) == len(synthetic_data)
    assert len(dy_pred) == len(synthetic_data)

def test_model_save_load(synthetic_data, tmp_path):
    model1 = IcebergDisplacementModel()
    model1.train(synthetic_data)
    
    model_dir = tmp_path / "models"
    model1.save(model_dir)
    
    model2 = IcebergDisplacementModel()
    model2.load(model_dir)
    
    dx_pred1, dy_pred1 = model1.predict(synthetic_data)
    dx_pred2, dy_pred2 = model2.predict(synthetic_data)
    
    np.testing.assert_array_almost_equal(dx_pred1, dx_pred2)
    np.testing.assert_array_almost_equal(dy_pred1, dy_pred2)

def test_feature_importance(synthetic_data):
    model = IcebergDisplacementModel()
    model.train(synthetic_data)
    
    imp_df = model.feature_importance()
    assert len(imp_df) == len(FEATURE_COLS)
    assert list(imp_df.columns) == ['feature', 'importance_dx', 'importance_dy', 'importance_mean']
    assert set(imp_df['feature']) == set(FEATURE_COLS)

def test_evaluate_returns_metrics(synthetic_data):
    model = IcebergDisplacementModel()
    model.train(synthetic_data)
    
    metrics = model.evaluate(synthetic_data)
    expected_keys = ['rmse_dx', 'rmse_dy', 'rmse_total', 'mae_total', 'mean_position_error_km', 'r2_dx', 'r2_dy']
    for key in expected_keys:
        assert key in metrics
        assert isinstance(metrics[key], float)
