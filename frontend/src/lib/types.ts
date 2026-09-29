export interface Coordinate {
  lat: number;
  lon: number;
}

export interface VesselProfile {
  id: string;
  name: string;
  maxSpeedKnots: number;
  maxIceConcentration: number;
  iceSpeedFactor: number;
  draftM: number;
  iceClass: string;
  description: string;
}

export type RiskLevel = 'High' | 'Medium' | 'Low';

export interface DepartureOption {
  departureTime: string;
  // A RiskLevel for planned routes; the failure reason when no route was found.
  riskSummary: RiskLevel | string;
  eta: string;
  travelTimeHours: number;
  distanceKm: number;
  maxIceExposure: number; // fraction 0-1
  icebergProximityEvents: number;
  icebergsAvoided: number;
  predictionConfidence: number; // fraction 0-1
  routeGeoJSON: GeoJSON.FeatureCollection;
}

export interface VoyageRequest {
  pointA: Coordinate;
  pointB: Coordinate;
  vesselId: string;
  windowStart: string; // ISO 8601 with timezone (UTC)
  windowEnd: string;
}

export interface VoyageResult {
  id: string;
  status: 'completed' | 'failed';
  vesselId: string;
  options: DepartureOption[];
  icebergsGeoJSON: GeoJSON.FeatureCollection;
  summaryMessage: string;
}

export interface DataFreshness {
  source: string;
  lastUpdated: string | null;
  ageMinutes: number;
  status: 'fresh' | 'stale' | 'unavailable' | 'synthetic';
}
