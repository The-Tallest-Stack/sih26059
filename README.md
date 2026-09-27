# Antarctic Voyage Decision Support System

> **SIH 2026 Problem Statement 26059:** AI-Enabled Antarctic Sea-Ice, Iceberg Trajectory, and Navigation Decision Support System.

## Overview
This is a **Human-in-the-Loop Decision Support System** designed for Antarctic vessel voyage planning. 
Antarctic voyages can take multiple days, and sea ice, icebergs, ocean currents, winds, and waves can evolve significantly during the trip. A route planned from conditions observed at departure may encounter substantially different conditions later.

This system introduces **Departure Time as a first-class variable**. Instead of just answering *"Which route should I take?"*, it answers *"If I leave at 2 PM vs. 8 PM, how does my risk profile, fuel consumption, and ETA change based on forecasted conditions?"*

*Note: This is an advisory tool for human navigators, not an autonomous ship control system.*

## Tech Stack
* **Frontend:** Next.js 14, React, TailwindCSS, MapLibre GL JS (3D Globe Projection)
* **Backend:** Python 3.12, FastAPI, Pydantic, Uvicorn
* **Machine Learning:** XGBoost (Error-correction over a Physics-based Free-Drift Baseline)
* **Data Processing:** Xarray, Pandas, GeoPandas, Shapely (Spatiotemporal multidimensional grid alignment)
* **Data Sources:** Copernicus Marine Service, Copernicus Climate Data Store (ERA5), NASA Earthdata (NSIDC), USNIC, BYU

## Architecture

The system is decoupled into several core pipelines:
1. **Data Acquisition & Alignment:** Fuses legacy point-based iceberg observations with gridded NetCDF environmental variables across varying map projections.
2. **Trajectory Prediction:** Combines a classical physics-based free-drift model with an XGBoost correction layer to predict iceberg paths +6h, +12h... up to +72h.
3. **Dynamic Risk Map:** Fuses static constraints (bathymetry, land) with dynamic hazards (sea ice concentration, wind, waves).
4. **Time-Dependent A* Pathfinding:** A custom routing engine that adapts ship speed and risk based on the specific *arrival time* of the vessel at a given coordinate.
5. **Departure Optimizer:** Sweeps candidate departure times and aggregates comparative metrics for the frontend.

## How to Run Locally

### Option 1: 1-Click Start (Windows)
Simply double-click the `start_demo.bat` file located in the root of this project. It will automatically start both the backend API and the frontend website, and open your browser to `http://localhost:3000`.

### Option 2: Manual Start

**1. Start the Backend API**
```bash
cd backend
python -m venv .venv
# (Activate venv: .\.venv\Scripts\activate on Windows, or source .venv/bin/activate on Mac/Linux)
pip install -e .

# Run the server
set PYTHONPATH=src
uvicorn antarctic_dss.api.app:app --host 0.0.0.0 --port 8000 --reload
```

**2. Start the Frontend UI**
```bash
cd frontend
npm install
npm run dev
```

The interactive dashboard will be available at [http://localhost:3000](http://localhost:3000). The FastAPI Swagger docs are available at [http://localhost:8000/docs](http://localhost:8000/docs).

## Configuration
Before running the ML pipelines, configure your API keys by creating a `.env` file in the root directory:
```env
COPERNICUS_USERNAME=your_email
COPERNICUS_PASSWORD=your_password
CDS_API_KEY=your_token
EARTHDATA_USERNAME=your_username
EARTHDATA_PASSWORD=your_password
```
