'use client';

import React from 'react';
import { DepartureOption } from '../lib/types';

interface DepartureComparisonProps {
  options: DepartureOption[];
  failed: boolean;
  selectedIdx: number;
  onSelectOption: (index: number) => void;
}

const getRiskColor = (risk: string) => {
  switch (risk) {
    case 'High': return 'bg-red-500/20 text-red-400 border-red-500/50';
    case 'Medium': return 'bg-yellow-500/20 text-yellow-400 border-yellow-500/50';
    case 'Low': return 'bg-green-500/20 text-green-400 border-green-500/50';
    default: return 'bg-gray-500/20 text-gray-400 border-gray-500/50';
  }
};

export default function DepartureComparison({ options, failed, selectedIdx, onSelectOption }: DepartureComparisonProps) {
  if (!options || options.length === 0) return null;

  return (
    <div className="mt-4 space-y-4">
      <div className="flex flex-col gap-4">
        {options.map((option, idx) => (
          <div key={idx} className={`bg-gray-900 border rounded-lg p-4 text-white flex flex-col relative overflow-hidden ${idx === selectedIdx && !failed ? 'border-blue-500' : 'border-gray-800'}`}>
            {idx === 0 && !failed && options.length > 1 && (
              <span className="text-xs font-bold text-blue-400 mb-2">Recommended departure (lowest risk)</span>
            )}
            {failed ? (
              <div className="absolute inset-0 bg-red-900/95 p-4 flex flex-col items-center justify-center text-center z-10 border border-red-500 rounded-lg">
                <span className="text-red-200 font-bold mb-2">Route Failed</span>
                <span className="text-white text-sm px-4">{option.riskSummary}</span>
              </div>
            ) : null}
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
                <span>{option.travelTimeHours.toFixed(1)}h</span>
              </div>
              <div>
                <span className="text-gray-400 block">Distance</span>
                <span>{option.distanceKm.toFixed(0)} km</span>
              </div>
              <div>
                <span className="text-gray-400 block">Max Ice Exp.</span>
                <span>{(option.maxIceExposure * 100).toFixed(0)}%</span>
              </div>
              <div>
                <span className="text-gray-400 block">Iceberg Prox.</span>
                <span>{option.icebergProximityEvents} events</span>
              </div>
              <div>
                <span className="text-gray-400 block">Icebergs Avoided</span>
                <span className="text-green-400 font-bold">{option.icebergsAvoided}</span>
              </div>
              <div>
                <span className="text-gray-400 block">Confidence</span>
                <span>{(option.predictionConfidence * 100).toFixed(1)}%</span>
              </div>
              {option.riskBreakdown && (
                <div>
                  <span className="text-gray-400 block">Peak Wind / Waves</span>
                  <span>{option.riskBreakdown.max_wind_ms.toFixed(0)} m/s / {option.riskBreakdown.max_wave_m.toFixed(1)} m</span>
                </div>
              )}
            </div>
            {option.riskScore !== undefined && option.riskBreakdown && (
              <div className="text-xs text-gray-400 mb-3" title="Risk score = 45% ice + 35% icebergs + 20% weather. Low < 0.30 <= Medium < 0.70 <= High">
                Risk score <span className="text-white font-semibold">{option.riskScore.toFixed(2)}</span>
                {' '}= ice {option.riskBreakdown.ice.toFixed(2)} · icebergs {option.riskBreakdown.icebergs.toFixed(2)} · weather {option.riskBreakdown.weather.toFixed(2)}
              </div>
            )}

            <button
              onClick={() => onSelectOption(idx)}
              className="w-full bg-gray-800 hover:bg-gray-700 text-white font-medium py-2 rounded transition-colors mt-auto border border-gray-700"
            >
              {idx === selectedIdx ? 'Showing on Map' : 'View Route'}
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}
