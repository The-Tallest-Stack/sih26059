'use client';

import React, { useEffect, useRef } from 'react';
import maplibregl from 'maplibre-gl';
import 'maplibre-gl/dist/maplibre-gl.css';

interface AntarcticMapProps {
  routeGeoJSON?: GeoJSON.FeatureCollection;
  icebergsGeoJSON?: GeoJSON.FeatureCollection;
  riskMapGeoJSON?: GeoJSON.FeatureCollection;
  onMapClick?: (coord: { lat: number; lon: number }) => void;
}

export default function AntarcticMap({
  routeGeoJSON,
  icebergsGeoJSON,
  riskMapGeoJSON,
  onMapClick,
}: AntarcticMapProps) {
  const mapContainer = useRef<HTMLDivElement>(null);
  const map = useRef<maplibregl.Map | null>(null);

  // Store latest onMapClick to avoid stale closures in map event listener
  const onMapClickRef = useRef(onMapClick);
  useEffect(() => {
    onMapClickRef.current = onMapClick;
  }, [onMapClick]);

  useEffect(() => {
    if (!mapContainer.current) return;

    map.current = new maplibregl.Map({
      container: mapContainer.current,
      style: 'https://demotiles.maplibre.org/style.json',
      center: [0, -75],
      zoom: 2.5,
      // @ts-expect-error: projection globe is supported in newer maplibre versions
      projection: { type: 'globe' },
    });

    const m = map.current;

    m.addControl(new maplibregl.NavigationControl(), 'top-right');

    m.on('load', () => {
      // Risk Map Layer
      m.addSource('risk-map', {
        type: 'geojson',
        data: riskMapGeoJSON || { type: 'FeatureCollection', features: [] },
      });
      m.addLayer({
        id: 'risk-map-layer',
        type: 'fill',
        source: 'risk-map',
        paint: {
          'fill-color': '#ff0000',
          'fill-opacity': ['get', 'risk'],
        },
      });

      // Icebergs Layer
      m.addSource('icebergs', {
        type: 'geojson',
        data: icebergsGeoJSON || { type: 'FeatureCollection', features: [] },
      });
      m.addLayer({
        id: 'icebergs-layer',
        type: 'circle',
        source: 'icebergs',
        paint: {
          'circle-color': '#00e5ff',
          'circle-radius': 6,
          'circle-stroke-width': 1,
          'circle-stroke-color': '#ffffff',
        },
      });

      // Vessel Route Layer
      m.addSource('vessel-route', {
        type: 'geojson',
        data: routeGeoJSON || { type: 'FeatureCollection', features: [] },
      });
      m.addLayer({
        id: 'vessel-route-layer',
        type: 'line',
        source: 'vessel-route',
        paint: {
          'line-color': '#ff3366',
          'line-width': 3,
        },
      });
    });

    m.on('click', (e) => {
      if (onMapClickRef.current) {
        onMapClickRef.current({ lat: e.lngLat.lat, lon: e.lngLat.lng });
      }
    });

    return () => {
      m.remove();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []); // Run once on mount

  // Update sources when props change
  useEffect(() => {
    if (!map.current || !map.current.isStyleLoaded()) return;

    const updateSource = (id: string, data: GeoJSON.FeatureCollection | GeoJSON.Feature | Record<string, unknown>) => {
      const source = map.current?.getSource(id) as maplibregl.GeoJSONSource;
      if (source && data) {
        source.setData(data);
      }
    };

    updateSource('vessel-route', routeGeoJSON || { type: 'FeatureCollection', features: [] });
    updateSource('icebergs', icebergsGeoJSON || { type: 'FeatureCollection', features: [] });
    updateSource('risk-map', riskMapGeoJSON || { type: 'FeatureCollection', features: [] });
  }, [routeGeoJSON, icebergsGeoJSON, riskMapGeoJSON]);

  return (
    <div
      ref={mapContainer}
      className="w-full h-full min-h-[600px] bg-gray-900 rounded-lg overflow-hidden"
    />
  );
}
