'use client';

import React from 'react';
import { DepartureOption } from '../lib/types';

interface DepartureComparisonProps {
  options: DepartureOption[];
  onSelectOption: (index: number) => void;
}

const getRiskColor = (risk: 'High' | 'Medium' | 'Low') => {
  switch (risk) {
    case 'High': return 'bg-red-500/20 text-red-400 border-red-500/50';
    case 'Medium': return 'bg-yellow-500/20 text-yellow-400 border-yellow-500/50';
    case 'Low': return 'bg-green-500/20 text-green-400 border-green-500/50';
    default: return 'bg-gray-500/20 text-gray-400 border-gray-500/50';
  }
};

export default function DepartureComparison({ options, onSelectOption }: DepartureComparisonProps) {
  if (!options || options.length === 0) return null;

  return (
    <div className="mt-4 space-y-4">
      <div className="flex flex-col gap-4">
        {options.map((option, idx) => (
          <div key={idx} className="bg-gray-900 border border-gray-800 rounded-lg p-4 text-white flex flex-col">
            <div className="flex justify-between items-start mb-4">
              <div>
                <div className="text-sm text-gray-400">Departure Time</div>
                <div className="font-semibold">{new Date(option.departureTime).toLocaleString()}</div>
              </div>
              <span className={`px-2 py-1 text-xs font-bold rounded border ${getRiskColor(option.riskSummary)}`}>
                {option.riskSummary} Risk
              </span>
            </div>

            <div className="grid grid-cols-2 gap-2 text-sm mb-4 flex-grow">
              <div>
                <span className="text-gray-400 block">ETA</span>
                <span>{new Date(option.eta).toLocaleDateString()}</span>
              </div>
              <div>
                <span className="text-gray-400 block">Travel Time</span>
                <span>{option.travelTimeHours}h</span>
              </div>
              <div>
                <span className="text-gray-400 block">Distance</span>
                <span>{option.distanceKm.toFixed(0)} km</span>
              </div>
              <div>
                <span className="text-gray-400 block">Max Ice Exp.</span>
                <span>{option.maxIceExposure}%</span>
              </div>
              <div>
                <span className="text-gray-400 block">Iceberg Prox.</span>
                <span>{option.icebergProximityEvents} events</span>
              </div>
              <div>
                <span className="text-gray-400 block">Confidence</span>
                <span>{option.predictionConfidence}%</span>
              </div>
            </div>

            <button
              onClick={() => onSelectOption(idx)}
              className="w-full bg-gray-800 hover:bg-gray-700 text-white font-medium py-2 rounded transition-colors mt-auto border border-gray-700"
            >
              View Route
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}
