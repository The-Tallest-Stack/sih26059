'use client';

import React, { useState, useEffect, useCallback } from 'react';
import dynamic from 'next/dynamic';
import { Coordinate, VoyageRequest, VoyageResult, DepartureOption, DataFreshness } from '../lib/types';
import { planVoyage, fetchCurrentIcebergs, fetchDataFreshness } from '../lib/api';
import VoyageForm from '../components/VoyageForm';
import DepartureComparison from '../components/DepartureComparison';
import DataFreshnessBar from '../components/DataFreshnessBar';

// Dynamic import for MapLibre to avoid SSR issues
const AntarcticMap = dynamic(() => import('../components/AntarcticMap'), {
  ssr: false,
  loading: () => <div className="w-full h-full min-h-[600px] bg-gray-900 rounded-lg flex items-center justify-center text-gray-500">Loading Map...</div>
});

export default function Home() {
  const [pointA, setPointA] = useState<Coordinate | undefined>();
  const [pointB, setPointB] = useState<Coordinate | undefined>();
  const [settingPoint, setSettingPoint] = useState<'A' | 'B'>('A');
  
  const [voyages, setVoyages] = useState<{result: VoyageResult, selectedIdx: number}[]>([]);
  const [icebergsGeoJSON, setIcebergsGeoJSON] = useState<GeoJSON.FeatureCollection | undefined>();
  const [freshness, setFreshness] = useState<DataFreshness[]>([]);
  
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    // Initial data fetch
    const loadInitialData = async () => {
      try {
        const [icebergs, freshnessData] = await Promise.all([
          fetchCurrentIcebergs().catch(() => undefined),
          fetchDataFreshness().catch(() => [])
        ]);
        if (icebergs) setIcebergsGeoJSON(icebergs);
        if (freshnessData) setFreshness(freshnessData as DataFreshness[]);
      } catch (err) {
        console.error("Failed to load initial data", err);
      }
    };
    loadInitialData();
  }, []);

  const handleMapClick = useCallback((coord: { lat: number; lon: number }) => {
    if (settingPoint === 'A') {
      setPointA(coord);
      setSettingPoint('B');
    } else {
      setPointB(coord);
      setSettingPoint('A');
    }
  }, [settingPoint]);

  const handlePlanVoyage = async (request: VoyageRequest) => {
    setIsLoading(true);
    setError(null);
    try {
      const result = await planVoyage(request);
      setVoyages(prev => [...prev, { result, selectedIdx: 0 }]);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : String(err));
      console.error(err);
    } finally {
      setIsLoading(false);
    }
  };

  const deleteVoyage = (index: number) => {
    setVoyages(prev => prev.filter((_, i) => i !== index));
  };

  // Combine all selected routes into a single GeoJSON FeatureCollection to render them all
  const combinedRoutesGeoJSON: GeoJSON.FeatureCollection = {
    type: 'FeatureCollection',
    features: voyages.map(v => {
      const option = v.result.options[v.selectedIdx];
      return option?.routeGeoJSON?.features || [];
    }).flat() as GeoJSON.Feature[]
  };

  return (
    <main className="min-h-screen p-4 pb-16 max-w-[1920px] mx-auto flex flex-col">
      <header className="mb-6">
        <h1 className="text-3xl font-bold">Antarctic Voyage Decision Support System</h1>
        <p className="text-gray-400">AI-Enabled Route Planning & Risk Assessment</p>
      </header>

      <div className="flex-grow flex flex-col xl:flex-row gap-6 overflow-hidden max-h-[calc(100vh-120px)]">
        {/* Left Sidebar - Controls & Info */}
        <div 
          className="w-full xl:w-[450px] flex-shrink-0 space-y-6 flex flex-col overflow-y-auto overflow-x-hidden pr-2 pb-4"
          style={{ resize: 'horizontal', minWidth: '350px', maxWidth: '50vw' }}
        >
          <VoyageForm 
            onSubmit={handlePlanVoyage} 
            pointA={pointA} 
            pointB={pointB} 
            setPointA={setPointA}
            setPointB={setPointB}
          />
          
          {error && (
            <div className="bg-red-500/20 border border-red-500 text-red-100 p-4 rounded">
              {error}
            </div>
          )}

          {isLoading && (
            <div className="bg-blue-500/20 border border-blue-500 text-blue-100 p-4 rounded text-center">
              Planning voyage... This may take a moment.
            </div>
          )}

          {voyages.map((v, idx) => (
            <div key={idx} className="relative border border-gray-700 p-4 rounded-lg bg-gray-900/50">
              <button 
                onClick={() => deleteVoyage(idx)} 
                className="absolute top-2 right-2 text-red-500 hover:text-red-400 text-sm font-bold bg-gray-800 px-2 py-1 rounded"
              >
                Delete
              </button>
              <h3 className="font-bold text-white mb-2">Voyage {idx + 1}</h3>
              <DepartureComparison 
                options={v.result.options} 
                onSelectOption={(newIdx) => {
                  setVoyages(prev => {
                    const newVoyages = [...prev];
                    newVoyages[idx].selectedIdx = newIdx;
                    return newVoyages;
                  });
                }} 
              />
            </div>
          ))}
        </div>

        {/* Right Main Area - Map */}
        <div className="flex-grow min-h-[600px] xl:min-h-0 relative rounded-lg overflow-hidden border border-gray-800 flex flex-col">
          <div className="absolute top-4 left-4 z-10 bg-gray-900/80 p-2 rounded text-sm pointer-events-none border border-gray-700">
            Currently setting: <span className="font-bold text-blue-400">Point {settingPoint}</span>
          </div>
          
          <AntarcticMap 
            onMapClick={handleMapClick}
            routeGeoJSON={combinedRoutesGeoJSON}
            icebergsGeoJSON={icebergsGeoJSON}
            riskMapGeoJSON={voyages.length > 0 ? voyages[0].result.seaIceGeoJSON : undefined}
          />
        </div>
      </div>

      <DataFreshnessBar sources={freshness} />
    </main>
  );
}
