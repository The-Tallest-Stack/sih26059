# Antarctic Voyage Decision Support System — Documentation

Departure-time-aware voyage planning for Antarctic waters: live icebergs, sea-ice / ocean /
weather forecasts, an iceberg drift model, and a risk-weighted, time-dependent route planner.

---

## 1. Repository layout

```
sih26059/
├── backend/                     FastAPI service + all science code (Python)
│   ├── src/antarctic_dss/
│   │   ├── api/                 HTTP endpoints (app.py, routes_voyage.py, routes_data.py, schemas.py)
│   │   ├── routing/             risk_map.py, astar.py, departure.py, vessel.py, bathymetry.py
│   │   ├── models/              trajectory.py, xgboost_model.py, physics_baseline.py,
│   │   │                        uncertainty.py, training.py, model_*.json (trained weights)
│   │   ├── data/                loaders: usnic_live, copernicus, era5, iceberg_tracks,
│   │   │                        alignment, training_table, sync_forecasts; land/ice-shelf GeoJSON
│   │   ├── utils/               geo.py (distances, projections), time_utils.py
│   │   └── config.py            paths + credentials (.env)
│   ├── data/cache/forecast.zarr 10-day forecast cache used by the API (git-ignored)
│   └── tests/                   pytest suite (46 tests)
├── frontend/                    Next.js 14 + MapLibre web app
│   └── src/app/ (page.tsx = Route Planner, predictor/page.tsx = Trajectory Predictor)
│       src/components/, src/lib/ (api.ts, types.ts)
├── scripts/                     download_*.py, train_pipeline.py, train_xgboost_only.py
├── data/                        raw downloads, processed tables (git-ignored)
├── docs/                        this file + TECHNICAL_APPROACH.md
└── start_demo.bat               one-click start (Windows)
```

---

## 2. Setup

**Requirements:** Python 3.9+, Node 18+, ~30 GB disk for training data (optional).

```bash
# Backend
cd backend
python -m venv .venv
.venv\Scripts\activate            # Windows  (source .venv/bin/activate on Mac/Linux)
pip install -e ".[data,dev]"

# Frontend
cd frontend
npm install
```

**Credentials** — create `.env` in the project root (see `.env.example`):

```env
COPERNICUS_USERNAME=...
COPERNICUS_PASSWORD=...
CDS_API_KEY=...            # ERA5 (also needs ~/.cdsapirc)
EARTHDATA_USERNAME=...
EARTHDATA_PASSWORD=...
```

---

## 3. Running

**One click (Windows):** `start_demo.bat` → backend on :8000, frontend on :3000.
Make sure no old `node` server holds port 3000 first (Next.js silently moves to 3001).

**Manual:**
```bash
cd backend && set PYTHONPATH=src && uvicorn antarctic_dss.api.app:app --port 8000
cd frontend && npm run dev
```

**Before a demo — refresh the forecast** (otherwise the freshness bar shows "stale"):
```bash
cd backend && set PYTHONPATH=src && python src/antarctic_dss/data/sync_forecasts.py
```

API docs: http://localhost:8000/docs

---

## 4. Data sources

| Data | Source | Used for | How it's fetched |
|---|---|---|---|
| Live icebergs (≥10 NM) | US National Ice Center CSV | Hazards, predictor | Live, cached 30 min |
| Sea ice (conc., thickness, drift) | Copernicus GLO12 forecast | Risk map, routing speed, drift inputs | `sync_forecasts.py` (10 days) |
| Surface currents | Copernicus GLO12 currents forecast | Drift model inputs | `sync_forecasts.py` |
| Waves (significant height) | Copernicus wave forecast | Risk map | `sync_forecasts.py` |
| 10 m wind | ECMWF open-data IFS | Risk map, drift inputs | `sync_forecasts.py` |
| Bathymetry | Copernicus GLO12 static `deptho` | Depth/draft check | `download_copernicus.py --dataset bathymetry` |
| Land + ice shelves | Natural Earth 50m | Land mask, island edge check | bundled GeoJSON |
| Historical iceberg tracks | BYU/NIC consolidated DB v8 | Training targets | `download_byu_tracks.py` |
| Historical wind | ERA5 reanalysis | Training inputs | `download_era5.py --wind-only` |
| Historical ocean + sea ice | Copernicus GLORYS reanalysis | Training inputs | `download_copernicus.py` |

---

## 5. API reference

| Method | Endpoint | Description |
|---|---|---|
| POST | `/api/voyage/plan` | Plan a voyage: sweeps the departure window, returns the 3 lowest-risk options |
| GET | `/api/voyage/{id}/options` | Re-fetch a planned voyage |
| GET | `/api/icebergs/current` | Live USNIC icebergs (GeoJSON) |
| GET | `/api/icebergs/predict_all` | Predicted trajectories, all icebergs (+6 … +72 h) |
| GET | `/api/icebergs/{id}/trajectory?horizon_hours=72` | One iceberg's predicted trajectory |
| GET | `/api/environment/seaice?time=` | Sea-ice concentration overlay (1°) |
| GET | `/api/environment/risk-map?vessel_id=&time=` | Per-vessel risk overlay (1°) |
| GET | `/api/data/freshness` | Status of each data source (fresh / stale / unavailable / synthetic) |
| GET | `/api/vessels` | Vessel profiles |
| GET | `/health` | Health check |

**Plan request example**
```json
{
  "point_a": {"lat": -62.2, "lon": -58.9},
  "point_b": {"lat": -64.8, "lon": -64.1},
  "vessel_id": "icebreaker_pc1",
  "window_start": "2026-09-29T00:00:00Z",
  "window_end":   "2026-09-30T00:00:00Z",
  "interval_hours": 6
}
```
Response: `status` (completed/failed), `options[]` (departure time, ETA, travel time, distance,
max ice, iceberg proximity events, icebergs avoided, confidence, route GeoJSON),
`comparison_summary` (incl. `iceberg_positions`: `predicted` or `current`).

---

## 6. Vessel profiles

| ID | Class | Max ice conc. | Max ice thickness | Speed |
|---|---|---|---|---|
| `icebreaker_pc1` | PC1 heavy icebreaker | 100% | 4.0 m | 18 kn |
| `icebreaker_pc2` | PC2 | 100% | 3.0 m | 17 kn |
| `icebreaker_pc3` | PC3 | 100% | 2.5 m | 16 kn |
| `icebreaker_pc4` | PC4 | 90% | 1.5 m | 15 kn |
| `icebreaker_pc5` | PC5 | 80% | 1.2 m | 15 kn |
| `research_vessel` | Ice class 1A | 50% | 0.8 m | 12 kn |
| `supply_vessel` | No ice class | 15% | 0.3 m | 14 kn |

Add more in `backend/src/antarctic_dss/routing/vessel.py` — the UI picks them up automatically.

---

## 7. Training the drift model

```bash
# Download training data (per year: ~1 GB ERA5 wind, ~3 GB sea ice, ~2 GB currents)
python scripts/download_era5.py --wind-only --start-year 2020 --end-year 2022
python scripts/download_copernicus.py --dataset all --start-year 2020 --end-year 2022
python scripts/download_copernicus.py --dataset bathymetry

# Align + train (writes data/processed/training_table.parquet and model artifacts)
python scripts/train_pipeline.py --years 2020-2023
# Retrain only (reuses the table)
python scripts/train_xgboost_only.py --years 2020-2023
```
Outputs in `backend/src/antarctic_dss/models/`: `model_dx.json`, `model_dy.json`,
`uncertainty.json`, `training_metrics.json` (test error vs physics and no-motion baselines,
per-season breakdown, feature importance).

**Model specifics**

| Item | Value |
|---|---|
| Algorithm | XGBoost gradient-boosted trees, two regressors (east `dx`, north `dy`) |
| Target | Iceberg displacement in metres per 24 h (east/north), between consecutive *real* satellite fixes 1–7 days apart, normalised per day |
| Features (14) | lat, lon, size_km², wind u/v, ocean current u/v, sea-ice drift u/v, sea-ice concentration, month sin/cos, physics free-drift dx/dy |
| Physics baseline | v = current + 2.5% × wind rotated −25°; follows sea-ice drift when concentration ≥ 80% |
| Loss | Pseudo-Huber (slope 2 km): robust to noisy position fixes |
| Hyperparameters | 500 trees max, depth 7, learning rate 0.03, subsample 0.8, colsample 0.8, min_child_weight 5, early stopping 50 rounds on validation |
| Data cleaning | Real fixes only (no interpolated positions), stale repeats removed, jumps > 80 km/day removed, grounded icebergs (< 0.5 km/day over a week in < 600 m water) excluded from training |
| Split | Chronological: train 2020–2021, validate 2022, test 2023 (3+ years); single year: train Jan–Jul, validate Aug–Sep, test Oct–Dec |
| Forcing alignment | Wind (ERA5), currents and sea ice (GLORYS) averaged over each displacement window at the nearest grid point |
| Uncertainty | Radius = 68th-percentile validation error per hour × horizon × (1 + sea-ice concentration) |
| Multi-step prediction | Model applied repeatedly (+6, +12, … h) with forecast forcing at each step; icebergs stop at land |

**Current results** (trained 2020–2021, validated 2022, tested on unseen 2023; mean 24 h position error):

| Test set | XGBoost | No-motion | Physics |
|---|---|---|---|
| Free-drifting (1,960 fixes) | **6.71 km** | 8.56 km | 13.50 km |
| Including grounded (2,728) | **6.14 km** | 7.75 km | – |
| Summer (DJF) / Autumn (MAM) / Winter (JJA) / Spring (SON) | 5.39 / 6.75 / 8.08 / 4.36 | 5.76 / 8.46 / 11.44 / 4.87 | 12.5 / 12.9 / 15.2 / 11.7 |

R² 0.34 (east) / 0.29 (north). Top features: sea-ice drift v/u, physics dx, longitude, current v.

**Automatic gate:** voyage planning uses *predicted* iceberg drift only if
`training_metrics.json` shows the model beat the no-motion baseline on the test year;
otherwise it uses last observed positions.

---

## 8. Testing

```bash
cd backend && set PYTHONPATH=src && python -m pytest -q     # 46 tests, offline
cd frontend && npx tsc --noEmit && npx next lint
```

---

## 9. Known limitations

- USNIC tracks only large icebergs (≥10 NM, ~30–40 at a time); small icebergs are not individually tracked.
- Route grid is 0.5°: good for ocean-scale planning, coarse near coasts.
- Wave forecast has no values inside sea ice (wave model limitation).
- Voyage results are stored in memory (lost on restart); no authentication; CORS is localhost-only.
- Training positions (ASCAT) have a few km of position error, which limits achievable accuracy.
