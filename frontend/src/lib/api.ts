import { VoyageRequest, VoyageResult, DataFreshness, VesselProfile } from './types';

// Relative by default: requests go to this website, which forwards /api to the backend
// (next.config.mjs). Set NEXT_PUBLIC_API_URL only to call a backend directly.
export const API_BASE = process.env.NEXT_PUBLIC_API_URL || '';

async function getJSON<T>(path: string, what: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`);
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new Error(`Failed to fetch ${what}: ${body?.detail || res.statusText}`);
  }
  return res.json();
}

export async function planVoyage(request: VoyageRequest): Promise<VoyageResult> {
  const payload = {
    point_a: request.pointA,
    point_b: request.pointB,
    vessel_id: request.vesselId,
    window_start: request.windowStart,
    window_end: request.windowEnd
  };

  const res = await fetch(`${API_BASE}/api/voyage/plan`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new Error(`Voyage planning failed: ${body?.detail || res.statusText}`);
  }
  const data = await res.json();
  return {
    id: data.id,
    status: data.status,
    vesselId: request.vesselId,
    icebergsGeoJSON: data.icebergs_geojson,
    summaryMessage: data.comparison_summary?.message || '',
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    options: data.options.map((opt: any) => ({
      departureTime: opt.departure_time,
      riskSummary: opt.risk_summary,
      eta: opt.eta,
      travelTimeHours: opt.travel_time_hours,
      distanceKm: opt.distance_km,
      maxIceExposure: opt.max_ice_concentration_en_route,
      icebergProximityEvents: opt.iceberg_proximity_events,
      icebergsAvoided: opt.icebergs_avoided || 0,
      predictionConfidence: opt.prediction_confidence,
      routeGeoJSON: opt.route_geojson
    }))
  };
}

export function fetchCurrentIcebergs(): Promise<GeoJSON.FeatureCollection> {
  return getJSON('/api/icebergs/current', 'icebergs');
}

export function fetchIcebergPredictions(): Promise<GeoJSON.FeatureCollection> {
  return getJSON('/api/icebergs/predict_all', 'iceberg predictions');
}

export function fetchRiskMap(vesselId: string, time?: string): Promise<GeoJSON.FeatureCollection> {
  const params = new URLSearchParams({ vessel_id: vesselId });
  if (time) params.set('time', time);
  return getJSON(`/api/environment/risk-map?${params}`, 'risk map');
}

export async function fetchVessels(): Promise<VesselProfile[]> {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const data = await getJSON<any[]>('/api/vessels', 'vessels');
  return data.map(v => ({
    id: v.id,
    name: v.name,
    maxSpeedKnots: v.max_speed_knots,
    maxIceConcentration: v.max_ice_concentration,
    iceSpeedFactor: v.ice_speed_factor,
    draftM: v.draft_m,
    iceClass: v.ice_class,
    description: v.description,
  }));
}

export async function fetchDataFreshness(): Promise<DataFreshness[]> {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const data = await getJSON<any[]>('/api/data/freshness', 'data freshness');
  return data.map(s => ({
    source: s.source,
    lastUpdated: s.last_updated,
    ageMinutes: s.age_minutes,
    status: s.status,
  }));
}
