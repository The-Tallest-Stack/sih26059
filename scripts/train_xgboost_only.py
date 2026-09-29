"""Retrain the iceberg displacement model from an existing aligned training table.

    python scripts/train_xgboost_only.py [--year 2023]

Run train_pipeline.py first to create data/processed/training_table.parquet.
"""
import argparse
import sys
from pathlib import Path

import pandas as pd

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR / "backend" / "src"))

from antarctic_dss.models.training import chronological_split_dates, train_and_evaluate

TABLE_PATH = ROOT_DIR / "data" / "processed" / "training_table.parquet"
MODEL_DIR = ROOT_DIR / "backend" / "src" / "antarctic_dss" / "models"

def run_training(years):
    if not TABLE_PATH.exists():
        print(f"Error: {TABLE_PATH} not found. Run scripts/train_pipeline.py first.")
        return
    table = pd.read_parquet(TABLE_PATH)
    print(f"Loaded {len(table)} rows from {TABLE_PATH}")
    if train_and_evaluate(table, MODEL_DIR, *chronological_split_dates(years)):
        print(f"Saved model artifacts to {MODEL_DIR}")

def parse_years(value: str):
    """'2023' -> [2023]; '2019-2023' -> [2019, ..., 2023]; '2019,2021' -> [2019, 2021]."""
    if '-' in value:
        start, end = (int(v) for v in value.split('-'))
        return list(range(start, end + 1))
    return [int(v) for v in value.split(',')]

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--years", type=parse_years, default=[2023],
                        help="Year(s) the table covers, e.g. 2023 or 2019-2023 (sets the split dates)")
    run_training(parser.parse_args().years)
