'use client';

import React, { useEffect, useState } from 'react';
import { Coordinate, VoyageRequest } from '../lib/types';
import { fetchVessels } from '../lib/api';

interface VoyageFormProps {
  onSubmit: (request: VoyageRequest) => void;
  pointA?: Coordinate;
  pointB?: Coordinate;
  setPointA: (c: Coordinate) => void;
  setPointB: (c: Coordinate) => void;
}

// Used until (or if) the backend's /api/vessels list loads.
const FALLBACK_VESSELS = [
  { id: 'icebreaker_pc5', name: 'Polar Class 5 Icebreaker' },
  { id: 'research_vessel', name: 'Research Vessel (Ice Class 1A)' },
  { id: 'supply_vessel', name: 'Supply Vessel (No Ice Class)' },
];

// <input type="datetime-local"> values have no timezone; interpret them as the user's
// local time and send UTC to the backend.
const localInputToUtcIso = (value: string) => new Date(value).toISOString();

export default function VoyageForm({ onSubmit, pointA, pointB, setPointA, setPointB }: VoyageFormProps) {
  const [vessels, setVessels] = useState(FALLBACK_VESSELS);
  const [vesselId, setVesselId] = useState(FALLBACK_VESSELS[0].id);
  const [windowStart, setWindowStart] = useState('');
  const [windowEnd, setWindowEnd] = useState('');

  useEffect(() => {
    fetchVessels()
      .then(list => { if (list.length > 0) setVessels(list); })
      .catch(err => console.error('Failed to load vessels, using defaults', err));
  }, []);

  const windowInvalid = !!windowStart && !!windowEnd && new Date(windowEnd) < new Date(windowStart);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!pointA || !pointB || !windowStart || !windowEnd || windowInvalid) return;
    onSubmit({
      pointA,
      pointB,
      vesselId,
      windowStart: localInputToUtcIso(windowStart),
      windowEnd: localInputToUtcIso(windowEnd),
    });
  };

  const handleCoordChange = (point: 'A' | 'B', field: 'lat' | 'lon', value: string) => {
    const num = parseFloat(value);
    if (isNaN(num)) return;
    if (point === 'A') {
      setPointA({ lat: field === 'lat' ? num : (pointA?.lat || 0), lon: field === 'lon' ? num : (pointA?.lon || 0) });
    } else {
      setPointB({ lat: field === 'lat' ? num : (pointB?.lat || 0), lon: field === 'lon' ? num : (pointB?.lon || 0) });
    }
  };

  return (
    <form onSubmit={handleSubmit} className="bg-gray-900 text-white p-6 rounded-lg space-y-4">
      <h2 className="text-xl font-bold mb-4">Plan Voyage</h2>
      
      <div>
        <label className="block text-sm font-medium mb-1">Vessel</label>
        <select
          value={vesselId}
          onChange={(e) => setVesselId(e.target.value)}
          className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-white"
        >
          {vessels.map((v) => (
            <option key={v.id} value={v.id}>
              {v.name}
            </option>
          ))}
        </select>
      </div>

      <div className="grid grid-cols-2 gap-4">
        <div>
          <label className="block text-sm font-medium mb-1">Window Start (local time)</label>
          <input
            type="datetime-local"
            value={windowStart}
            onChange={(e) => setWindowStart(e.target.value)}
            className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-white"
            required
          />
        </div>
        <div>
          <label className="block text-sm font-medium mb-1">Window End (local time)</label>
          <input
            type="datetime-local"
            value={windowEnd}
            onChange={(e) => setWindowEnd(e.target.value)}
            className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-white"
            required
          />
        </div>
      </div>
      {windowInvalid && (
        <p className="text-sm text-red-400">Window end must be after window start.</p>
      )}

      <div className="space-y-2 pt-2">
        <div className="p-3 bg-gray-800 rounded border border-gray-700">
          <span className="text-sm text-gray-400 block mb-2">Point A (Start) - Click map or type</span>
          <div className="flex gap-2">
            <input type="number" step="any" placeholder="Lat" value={pointA?.lat ?? ''} onChange={(e) => handleCoordChange('A', 'lat', e.target.value)} className="w-1/2 bg-gray-700 border border-gray-600 rounded px-2 py-1 text-sm text-white" />
            <input type="number" step="any" placeholder="Lon" value={pointA?.lon ?? ''} onChange={(e) => handleCoordChange('A', 'lon', e.target.value)} className="w-1/2 bg-gray-700 border border-gray-600 rounded px-2 py-1 text-sm text-white" />
          </div>
        </div>
        
        <div className="p-3 bg-gray-800 rounded border border-gray-700">
          <span className="text-sm text-gray-400 block mb-2">Point B (Destination) - Click map or type</span>
          <div className="flex gap-2">
            <input type="number" step="any" placeholder="Lat" value={pointB?.lat ?? ''} onChange={(e) => handleCoordChange('B', 'lat', e.target.value)} className="w-1/2 bg-gray-700 border border-gray-600 rounded px-2 py-1 text-sm text-white" />
            <input type="number" step="any" placeholder="Lon" value={pointB?.lon ?? ''} onChange={(e) => handleCoordChange('B', 'lon', e.target.value)} className="w-1/2 bg-gray-700 border border-gray-600 rounded px-2 py-1 text-sm text-white" />
          </div>
        </div>
      </div>

      <button
        type="submit"
        disabled={!pointA || !pointB || windowInvalid}
        className="w-full bg-blue-600 hover:bg-blue-700 disabled:bg-gray-700 disabled:cursor-not-allowed text-white font-bold py-3 px-4 rounded mt-6 transition-colors"
      >
        Plan Voyage
      </button>
    </form>
  );
}
