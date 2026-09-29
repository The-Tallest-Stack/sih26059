'use client';

import React, { useState, useEffect, useCallback } from 'react';
import dynamic from 'next/dynamic';
import { Coordinate, VoyageRequest, VoyageResult, DataFreshness } from '../lib/types';
import { planVoyage, fetchCurrentIcebergs, fetchDataFreshness, fetchRiskMap } from '../lib/api';
import VoyageForm from '../components/VoyageForm';
import DepartureComparison from '../components/DepartureComparison';
import DataFreshnessBar from '../components/DataFreshnessBar';

// Dynamic import for MapLibre to avoid SSR issues
const AntarcticMap = dynamic(() => import('../components/AntarcticMap'), {
  ssr: false,
  loading: () => <div className="w-full h-full bg-gray-900 rounded-lg flex items-center justify-center text-gray-500">Loading Map...</div>
});

// Minimum cell risk (0-1) drawn by the optional risk overlay.
const RISK_OVERLAY_MIN = 0.3;

export default function Home() {
  const [pointA, setPointA] = useState<Coordinate | undefined>();
  const [pointB, setPointB] = useState<Coordinate | undefined>();
  const [settingPoint, setSettingPoint] = useState<'A' | 'B'>('A');
  
  const [voyages, setVoyages] = useState<{result: VoyageResult, selectedIdx: number}[]>([]);
  const [icebergsGeoJSON, setIcebergsGeoJSON] = useState<GeoJSON.FeatureCollection | undefined>();
  const [freshness, setFreshness] = useState<DataFreshness[]>([]);
  const [riskMapGeoJSON, setRiskMapGeoJSON] = useState<GeoJSON.FeatureCollection | undefined>();
  const [showRiskOverlay, setShowRiskOverlay] = useState(false);
  
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
        setFreshness(freshnessData);
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

  const selectOption = (voyageIdx: number, optionIdx: number) => {
    setVoyages(prev => prev.map((v, i) => (i === voyageIdx ? { ...v, selectedIdx: optionIdx } : v)));
  };

  // Risk overlay for the most recent voyage: its vessel at the selected departure time.
  const latest = voyages[voyages.length - 1];
  const overlayVesselId = latest?.result.vesselId;
  const overlayTime = latest && latest.result.status === 'completed'
    ? latest.result.options[latest.selectedIdx]?.departureTime
    : undefined;
  useEffect(() => {
    if (!overlayVesselId || !showRiskOverlay) {
      setRiskMapGeoJSON(undefined);
      return;
    }
    let cancelled = false;
    fetchRiskMap(overlayVesselId, overlayTime)
      .then(data => {
        if (cancelled) return;
        // Only show cells with meaningful risk; low-risk cells would tint the whole map.
        setRiskMapGeoJSON({
          ...data,
          features: data.features.filter(f => (f.properties?.risk ?? 0) >= RISK_OVERLAY_MIN),
        });
      })
      .catch(err => console.error('Failed to load risk map', err));
    return () => { cancelled = true; };
  }, [overlayVesselId, overlayTime, showRiskOverlay]);

  // Combine all selected routes into a single GeoJSON FeatureCollection to render them all
  const routeColors = ['#ff3366', '#3b82f6', '#10b981', '#f59e0b', '#8b5cf6'];
  const combinedRoutesGeoJSON: GeoJSON.FeatureCollection = {
    type: 'FeatureCollection',
    features: voyages.map((v, idx) => {
      const option = v.result.options[v.selectedIdx];
      const features = option?.routeGeoJSON?.features || [];
      return features.map(f => ({
        ...f,
        properties: {
          ...f.properties,
          voyageIndex: idx + 1,
          color: routeColors[idx % routeColors.length]
        }
      }));
    }).flat() as GeoJSON.Feature[]
  };

  return (
    <main className="flex-1 min-h-0 p-3 w-full flex flex-col gap-2 overflow-y-auto xl:overflow-hidden">
      <div className="flex-1 min-h-0 flex flex-col xl:flex-row gap-3">
        {/* Left Sidebar - Controls & Info */}
        <div 
          className="w-full xl:w-[26rem] flex-shrink-0 space-y-4 flex flex-col xl:overflow-y-auto overflow-x-hidden pr-1"
          style={{ resize: 'horizontal', minWidth: '20rem', maxWidth: '50vw' }}
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
              {v.result.summaryMessage && (
                <p className="text-xs text-gray-400 mb-2">{v.result.summaryMessage}</p>
              )}
              <DepartureComparison
                options={v.result.options}
                failed={v.result.status === 'failed'}
                selectedIdx={v.selectedIdx}
                onSelectOption={(newIdx) => selectOption(idx, newIdx)}
              />
            </div>
          ))}
        </div>

        {/* Right Main Area - Map */}
        <div className="flex-1 min-h-[24rem] xl:min-h-0 relative rounded-lg overflow-hidden border border-gray-800 flex flex-col">
          <div className="absolute top-4 left-4 z-10 flex flex-col gap-2">
            <div className="bg-gray-900/80 p-2 rounded text-sm pointer-events-none border border-gray-700">
              Currently setting: <span className="font-bold text-blue-400">Point {settingPoint}</span>
            </div>
            {voyages.length > 0 && (
              <label className="bg-gray-900/80 p-2 rounded text-sm border border-gray-700 flex items-center gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={showRiskOverlay}
                  onChange={(e) => setShowRiskOverlay(e.target.checked)}
                />
                Show risk overlay
              </label>
            )}
          </div>
          
          <AntarcticMap 
            onMapClick={handleMapClick}
            routeGeoJSON={combinedRoutesGeoJSON}
            icebergsGeoJSON={icebergsGeoJSON}
            riskMapGeoJSON={riskMapGeoJSON}
          />
        </div>
      </div>

      <DataFreshnessBar sources={freshness} />
    </main>
  );
}
