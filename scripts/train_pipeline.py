"""Build the aligned training table from raw data and train the iceberg displacement model.

    python scripts/train_pipeline.py [--year 2023]

Writes data/processed/training_table.parquet and the model artifacts (model_dx.json,
model_dy.json, uncertainty.json, training_metrics.json) to backend/src/antarctic_dss/models.
Use train_xgboost_only.py to retrain from an existing table without re-aligning.
"""
import argparse
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR / "backend" / "src"))

from antarctic_dss.models.training import chronological_split_dates, build_training_table, train_and_evaluate

RAW_DIR = ROOT_DIR / "data" / "raw"
TABLE_PATH = ROOT_DIR / "data" / "processed" / "training_table.parquet"
MODEL_DIR = ROOT_DIR / "backend" / "src" / "antarctic_dss" / "models"

def run_pipeline(years):
    print(f"--- 1. Loading iceberg tracks and aligning environmental data ({years}) ---")
    table = build_training_table(RAW_DIR, years)
    if table.empty:
        print(f"No iceberg displacements found for {years}. Exiting.")
        return

    TABLE_PATH.parent.mkdir(parents=True, exist_ok=True)
    table.to_parquet(TABLE_PATH, index=False)
    print(f"Saved aligned training table ({len(table)} rows) to {TABLE_PATH}")

    print("\n--- 2. Training XGBoost model ---")
    metrics = train_and_evaluate(table, MODEL_DIR, *chronological_split_dates(years))
    if metrics:
        print(f"\nSaved model artifacts to {MODEL_DIR}")

def parse_years(value: str):
    """'2023' -> [2023]; '2019-2023' -> [2019, ..., 2023]; '2019,2021' -> [2019, 2021]."""
    if '-' in value:
        start, end = (int(v) for v in value.split('-'))
        return list(range(start, end + 1))
    return [int(v) for v in value.split(',')]

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--years", type=parse_years, default=[2023],
                        help="Year(s) with downloaded ERA5/Copernicus data, e.g. 2023 or 2019-2023 (default 2023)")
    run_pipeline(parser.parse_args().years)
