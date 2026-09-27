import datetime
import numpy as np
import pandas as pd
import pytest
import xarray as xr

from antarctic_dss.data.alignment import sample_latlon_grid
from antarctic_dss.data.training_table import apply_chronological_split, add_derived_features

def test_sample_latlon_returns_dict():
    # Create a tiny xarray dataset
    times = pd.date_range('2021-01-01', periods=3)
    lats = np.array([-60, -61])
    lons = np.array([45, 46])
    
    data = np.random.rand(3, 2, 2)
    
    ds = xr.Dataset(
        data_vars=dict(
            wind_speed=(["time", "lat", "lon"], data),
        ),
        coords=dict(
            time=times,
            lat=lats,
            lon=lons,
        ),
    )
    
    result = sample_latlon_grid(ds, lat=-60.5, lon=45.5, time='2021-01-02', variables=['wind_speed'])
    assert isinstance(result, dict)
    assert 'wind_speed' in result
    assert not np.isnan(result['wind_speed'])

def test_chronological_split_no_leakage():
    # Create sample df with dates from 2020-2024
    dates = pd.date_range(start='2020-01-01', end='2024-12-31', freq='M')
    df = pd.DataFrame({
        'timestamp': dates,
        'value': range(len(dates))
    })
    
    train, val, test = apply_chronological_split(df, train_end='2021-12-31', val_end='2023-12-31')
    
    assert train['timestamp'].max() <= pd.to_datetime('2021-12-31')
    assert val['timestamp'].min() > pd.to_datetime('2021-12-31')
    assert val['timestamp'].max() <= pd.to_datetime('2023-12-31')
    assert test['timestamp'].min() > pd.to_datetime('2023-12-31')
    
    assert len(train) + len(val) + len(test) == len(df)

def test_derived_features_columns():
    # Create sample data
    df = pd.DataFrame({
        'iceberg_id': [1, 1, 1],
        'timestamp': pd.to_datetime(['2021-01-01', '2021-02-01', '2021-03-01']),
        'target_dx': [10.0, 12.0, 15.0],
        'target_dy': [-5.0, -6.0, -8.0],
        'wind_u': [2.0, 3.0, 4.0],
        'wind_v': [1.0, 2.0, 3.0]
    })
    
    result_df = add_derived_features(df)
    
    expected_cols = [
        'lag1_dx', 'lag1_dy', 
        'month_sin', 'month_cos', 
        'physics_pred_dx', 'physics_pred_dy'
    ]
    
    for col in expected_cols:
        assert col in result_df.columns

    # Verify lag
    assert np.isnan(result_df['lag1_dx'].iloc[0])
    assert result_df['lag1_dx'].iloc[1] == 10.0
