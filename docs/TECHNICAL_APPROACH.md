# Technical Approach — Antarctic Voyage Decision Support System

*SIH Problem Statement 26059 — written to be slide-ready: each `##` section ≈ one slide.*

---

## 1. The Problem

Ships going to Antarctica face three moving hazards:
- **Sea ice** — can trap or damage ships that aren't built for it
- **Icebergs** — drift tens of km per day; collisions are catastrophic
- **Storms** — high wind and waves in the Southern Ocean

Today planners mostly ask *"which route?"*. But conditions change hour by hour, so the
**departure time** matters just as much.

> **Our question:** *"If I leave at 6 AM vs 6 PM, how do my risk, ETA and route change?"*

---

## 2. Our Solution in One Line

A web app where you **click a start and end point, pick a ship and a departure window**, and get
the **3 safest departure times**, each with a route that avoids ice, icebergs, shallow water
and storms — using **forecasts of where the icebergs will drift**.

---

## 3. System Overview

```
 LIVE DATA                     BRAINS                          OUTPUT
 ──────────                    ──────                          ──────
 US Ice Center icebergs ─┐
 Copernicus sea ice      ├──►  1. Iceberg drift predictor ─┐
 Copernicus currents     │     2. Risk map (per 6 hours)  ─┼─► 3 best departures
 Copernicus waves        │     3. Route finder (A*)       ─┘   + routes on a map
 ECMWF wind forecast     │     4. Departure optimizer          + risk, ETA, confidence
 Sea-floor depth ────────┘
```

**Tech stack:** Python (FastAPI, xarray, XGBoost, GeoPandas) · Next.js + MapLibre (web map)

---

## 4. Step 1 — Gathering the Data

| What | From | Why |
|---|---|---|
| Where icebergs are now | US National Ice Center | The hazards |
| Sea ice (how much, how thick, how it moves) | Copernicus Marine (EU) | Where ships can go |
| Ocean currents, waves | Copernicus Marine | Push icebergs, slow ships |
| Wind | ECMWF (European weather centre) | Pushes icebergs, storms |
| Sea-floor depth | Copernicus | Avoid running aground |

- All forecasts are downloaded for the **next 10 days** into a local cache.
- A **freshness bar** in the app shows whether each source is fresh, stale or missing — no hidden fake data.

---

## 5. Step 2 — Predicting Iceberg Drift (the AI part)

> **Who predicts what:** sea ice, wind, waves and currents come from official operational
> forecasts (Copernicus Marine, ECMWF) — physics models run on supercomputers.
> **Our AI predicts iceberg drift** and **optimises the route and departure time** on top of them.

**Two layers, working together:**

1. **Physics model** (classic oceanography):
   *iceberg speed ≈ ocean current + ~2.5% of wind speed, turned ~25° by Earth's rotation.*
   If sea ice is thick around it, the iceberg just moves with the ice.

2. **Machine learning correction (XGBoost):** learns what physics misses —
   iceberg size, season, location, sea-ice drift.

**Inputs →** wind, currents, sea-ice drift & concentration, iceberg size, month, physics estimate
**Output →** how far the iceberg moves east and north in 24 hours

We repeat this step by step to predict **+6 h … +72 h**, and draw an **uncertainty circle** that
grows over time (≈7 km after 1 day, ≈21 km after 3 days in open water; larger in sea ice).

---

## 5b. Model Specifics (at a glance)

| | |
|---|---|
| **Model** | XGBoost (boosted decision trees) — one for east-west, one for north-south movement |
| **Predicts** | How many metres the iceberg moves in 24 hours |
| **14 inputs** | Position, size, wind (2), ocean current (2), sea-ice drift (2), sea-ice cover, month (2), physics estimate (2) |
| **Loss** | Huber — ignores the occasional bad satellite fix instead of chasing it |
| **Size** | Up to 500 trees, depth 7, stops early when validation stops improving |
| **Data** | ~10,700 real satellite fixes, 112 icebergs, 2020–2023 |
| **Uncertainty** | Circle grows ~0.1–0.3 km per hour of forecast, larger in sea ice |

**Most important inputs (so far):** sea-ice drift, ocean currents, physics estimate —
the model learned real physics, not just "where icebergs usually are".

---

## 6. Training the Model — Doing It Honestly

- **Data:** real iceberg tracks from BYU/NASA satellites (2020–2023), matched with the
  weather and ocean conditions on each day.
- **Cleaning we had to do:**
  - Use only *real* satellite fixes (not interpolated in-between positions)
  - Remove *grounded* icebergs (stuck on the sea floor — they don't drift)
  - Throw out impossible jumps (bad fixes)
- **Fair testing:** train on older years, test on a year the model never saw.
- **Compared against two baselines:**
  - *Physics only*
  - *"Iceberg stays where it is"* — surprisingly hard to beat
- **Safety rule:** the route planner only uses the AI's predictions **if it beats both baselines.**

**Results on 2023 — a year the model never saw (1,960 free-drifting fixes), mean position error after 24 h:**

| Method | Error | |
|---|---|---|
| **Our model (physics + XGBoost)** | **6.7 km** | ✅ best |
| "Iceberg stays where it is" | 8.6 km | model is **22% better** |
| Physics only | 13.5 km | |

It wins in **every season** (winter: 8.1 vs 11.4 km — the hardest, ice-covered season) →
**so the route planner uses its predictions** to avoid where icebergs *will* be.

---

## 7. Step 3 — The Risk Map

We split the Antarctic ocean into a **grid of ~50 km cells**, rebuilt **every 6 hours** of the voyage.
Each cell gets a **risk cost**:

| Hazard | Effect |
|---|---|
| Sea ice | Cost grows sharply with concentration × thickness **relative to what the ship can handle** |
| Iceberg within 60 km (+ uncertainty) | Very large cost |
| Wind > 15 m/s, waves > 2 m | Extra cost |
| Too much / too thick ice for this ship | **Blocked** |
| Water too shallow for the ship's draft | **Blocked** |
| Land, ice shelves, small islands | **Blocked** |

Because icebergs are **predicted to move**, the same cell can be safe at 6 AM and dangerous at noon.

---

## 8. Step 4 — Finding the Route (A* search)

**A\*** is the classic "shortest path" algorithm used in GPS and games. We modified it:

- **Cost = travel time × (1 + risk)** → it trades a little extra time for a lot less risk
- **Time-dependent:** when the ship *arrives* at a cell, it looks up that cell's risk *at that time*
- **Ship speed changes** with ice: thicker ice → slower
- Handles crossing the **180° longitude line** and never cuts across islands

---

## 9. Step 5 — Choosing When to Leave

- Try a departure every **6 hours** across your window (up to 16 candidates)
- Run the route finder for each one
- Score each route: **ice exposure + iceberg proximity + weather**
- Show the **3 lowest-risk departures**, with:
  ETA · travel time · distance · max ice · icebergs avoided · confidence

---

## 10. Ship Classes (IACS Polar Classes)

| Ship | Can handle | Example behaviour (Weddell Sea, September) |
|---|---|---|
| PC1 heavy icebreaker | 4 m multi-year ice | Cuts straight through: ~1,700 km, 124 h |
| PC3 icebreaker | 2.5 m ice | Detours around thickest ice: ~2,900 km |
| PC5 ice-strengthened | 1.2 m first-year ice | Blocked |
| Supply ship (no ice class) | Open water only | Blocked |

Same start and end — **very different answers**, just like reality.

---

## 11. The Web App

- **Route Planner:** click Point A → Point B, choose ship + departure window → 3 options on a map
  (optional risk overlay, scale bar in km and nautical miles)
- **AI Trajectory Predictor:** all live icebergs with a time slider (0–72 h) and growing uncertainty circles
- **Data Freshness Bar:** live status of every data source

---

## 12. Engineering Quality

- **46 automated tests** (routing, ML pipeline, API, geography edge cases)
- Handles real-world edge cases: date line crossing, islands smaller than the grid, stale data, missing data
- Security: verified HTTPS downloads, no HTML injection from external data
- Fast: a full plan (10-day forecast, up to 16 departures) in ~5–15 seconds

---

## 13. Limitations & Future Work

| Today | Next |
|---|---|
| Only large icebergs (USNIC ≥ 10 NM) | Add small-iceberg density from satellite altimetry |
| 50 km route grid | Finer grid near coasts / ports |
| 4 years of training data | More years, SAR satellite iceberg detections |
| Single-machine demo | Cloud deployment, saved voyages, user accounts |
| Fuel not modelled | Add fuel/emissions to the departure trade-off |

---

## 14. Impact

- **Safer voyages** for research stations, supply ships and tourism
- **Better timing** — leaving a few hours later can avoid a storm or a drifting iceberg
- **Transparent** — every number comes with its data source, freshness and confidence
