'use client';

import React, { useState } from 'react';
import { Coordinate, VoyageRequest } from '../lib/types';

interface VoyageFormProps {
  onSubmit: (request: VoyageRequest) => void;
  pointA?: Coordinate;
  pointB?: Coordinate;
  setPointA: (c: Coordinate) => void;
  setPointB: (c: Coordinate) => void;
}

const VESSELS = [
  { id: 'icebreaker_pc5', name: 'Icebreaker PC5' },
  { id: 'research_vessel', name: 'Research Vessel 1A' },
  { id: 'supply_vessel', name: 'Supply Vessel' },
];

export default function VoyageForm({ onSubmit, pointA, pointB, setPointA, setPointB }: VoyageFormProps) {
  const [vesselId, setVesselId] = useState(VESSELS[0].id);
  const [windowStart, setWindowStart] = useState('');
  const [windowEnd, setWindowEnd] = useState('');

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!pointA || !pointB || !windowStart || !windowEnd) return;
    onSubmit({
      pointA,
      pointB,
      vesselId,
      windowStart,
      windowEnd,
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
          {VESSELS.map((v) => (
            <option key={v.id} value={v.id}>
              {v.name}
            </option>
          ))}
        </select>
      </div>

      <div className="grid grid-cols-2 gap-4">
        <div>
          <label className="block text-sm font-medium mb-1">Window Start</label>
          <input
            type="datetime-local"
            value={windowStart}
            onChange={(e) => setWindowStart(e.target.value)}
            className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-white"
            required
          />
        </div>
        <div>
          <label className="block text-sm font-medium mb-1">Window End</label>
          <input
            type="datetime-local"
            value={windowEnd}
            onChange={(e) => setWindowEnd(e.target.value)}
            className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-white"
            required
          />
        </div>
      </div>

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
        disabled={!pointA || !pointB}
        className="w-full bg-blue-600 hover:bg-blue-700 disabled:bg-gray-700 disabled:cursor-not-allowed text-white font-bold py-3 px-4 rounded mt-6 transition-colors"
      >
        Plan Voyage
      </button>
    </form>
  );
}
