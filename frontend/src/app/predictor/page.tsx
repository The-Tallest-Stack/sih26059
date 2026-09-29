'use client';

import React, { useState, useEffect } from 'react';
import dynamic from 'next/dynamic';
import { fetchIcebergPredictions } from '../../lib/api';

const PredictorMap = dynamic(() => import('../../components/PredictorMap'), {
  ssr: false,
  loading: () => <div className="w-full h-full bg-gray-900 rounded-lg flex items-center justify-center text-gray-500">Loading Map...</div>
});

const HORIZONS = [0, 6, 12, 18, 24, 48, 72];

export default function PredictorPage() {
  const [trajectories, setTrajectories] = useState<GeoJSON.FeatureCollection | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [sliderIndex, setSliderIndex] = useState(0);

  useEffect(() => {
    const fetchTrajectories = async () => {
      try {
        setTrajectories(await fetchIcebergPredictions());
      } catch (err: unknown) {
        if (err instanceof Error) {
          setError(err.message);
        } else {
          setError(String(err));
        }
      } finally {
        setLoading(false);
      }
    };
    fetchTrajectories();
  }, []);

  const selectedHorizon = HORIZONS[sliderIndex];

  return (
    <main className="flex-1 min-h-0 p-3 w-full flex flex-col">
      <div className="flex-shrink-0 bg-gray-900 border border-gray-800 p-4 rounded-lg mb-3 flex flex-col gap-3 shadow-xl z-10 relative">
        <div className="flex justify-between items-end">
          <div>
            <h1 className="text-2xl font-bold text-blue-400">AI Trajectory Predictor</h1>
            <p className="text-gray-400 text-sm">Visualize XGBoost predictions for all current USNIC icebergs.</p>
          </div>
          <div className="text-right">
            <div className="text-2xl font-black text-white">+{selectedHorizon}h</div>
            <div className="text-gray-500 text-sm uppercase font-bold tracking-wider">Forecast Horizon</div>
          </div>
        </div>
        
        <div className="relative pt-2 pb-1">
          <input 
            type="range" 
            min={0} 
            max={HORIZONS.length - 1} 
            value={sliderIndex} 
            onChange={(e) => setSliderIndex(parseInt(e.target.value))}
            className="w-full h-2 bg-gray-700 rounded-lg appearance-none cursor-pointer accent-blue-500"
          />
          <div className="flex justify-between text-xs text-gray-500 font-mono mt-2 px-1">
            {HORIZONS.map(h => (
              <span key={h}>{h}h</span>
            ))}
          </div>
        </div>
      </div>

      <div className="flex-1 min-h-0 relative rounded-lg overflow-hidden border border-gray-800 bg-gray-900 shadow-2xl">
        {loading && (
          <div className="absolute inset-0 flex items-center justify-center z-20 bg-gray-900/80 backdrop-blur-sm">
            <div className="flex flex-col items-center">
              <div className="w-8 h-8 border-4 border-blue-500 border-t-transparent rounded-full animate-spin mb-4"></div>
              <p className="text-blue-400 font-bold">Running XGBoost Models on live data...</p>
            </div>
          </div>
        )}
        
        {error && (
          <div className="absolute top-4 left-1/2 -translate-x-1/2 z-20 bg-red-900/80 border border-red-500 text-red-100 px-6 py-3 rounded-lg shadow-lg">
            Error: {error}
          </div>
        )}

        <PredictorMap 
          trajectoryGeoJSON={trajectories || undefined} 
          selectedHorizon={selectedHorizon} 
        />
      </div>
    </main>
  );
}
