'use client';

import React, { useEffect, useRef, useState } from 'react';
import maplibregl from 'maplibre-gl';
import 'maplibre-gl/dist/maplibre-gl.css';

// Popup content built with textContent: names come from external data (USNIC), so they
// must never be interpreted as HTML.
function popupLabel(text: string): HTMLElement {
  const div = document.createElement('div');
  div.className = 'p-1';
  const strong = document.createElement('strong');
  strong.className = 'text-gray-900';
  strong.textContent = text;
  div.appendChild(strong);
  return div;
}

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
  const [mapLoaded, setMapLoaded] = useState(false);

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
    // Scale bars: kilometres and nautical miles (the unit used for navigation and USNIC sizes).
    m.addControl(new maplibregl.ScaleControl({ maxWidth: 120, unit: 'metric' }), 'bottom-left');
    m.addControl(new maplibregl.ScaleControl({ maxWidth: 120, unit: 'nautical' }), 'bottom-left');

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
          // Impassable cells (for the selected vessel) in dark red, others by risk level.
          'fill-color': ['case', ['boolean', ['get', 'impassable'], false], '#7f1d1d', '#ef4444'],
          'fill-opacity': ['*', ['coalesce', ['get', 'risk'], 0], 0.3],
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
      
      const popup = new maplibregl.Popup({
        closeButton: false,
        closeOnClick: false,
        className: 'iceberg-popup'
      });

      m.on('mouseenter', 'icebergs-layer', (e) => {
        m.getCanvas().style.cursor = 'pointer';
        if (e.features && e.features[0] && e.features[0].geometry.type === 'Point') {
          const coordinates = e.features[0].geometry.coordinates.slice();
          const props = e.features[0].properties;
          const name = props?.Iceberg || 'Unknown';
          
          while (Math.abs(e.lngLat.lng - coordinates[0]) > 180) {
            coordinates[0] += e.lngLat.lng > coordinates[0] ? 360 : -360;
          }
          
          popup.setLngLat([coordinates[0], coordinates[1]])
            .setDOMContent(popupLabel(`Iceberg ${name}`))
            .addTo(m);
        }
      });

      m.on('mouseleave', 'icebergs-layer', () => {
        m.getCanvas().style.cursor = '';
        popup.remove();
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
          'line-color': ['coalesce', ['get', 'color'], '#ff3366'],
          'line-width': 4,
        },
      });
      
      m.on('mouseenter', 'vessel-route-layer', (e) => {
        m.getCanvas().style.cursor = 'pointer';
        if (e.features && e.features[0]) {
          const props = e.features[0].properties;
          if (props && props.voyageIndex) {
            popup.setLngLat(e.lngLat)
              .setDOMContent(popupLabel(`Voyage ${props.voyageIndex}`))
              .addTo(m);
          }
        }
      });

      m.on('mouseleave', 'vessel-route-layer', () => {
        m.getCanvas().style.cursor = '';
        popup.remove();
      });
      
      setMapLoaded(true);
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
    if (!map.current || !mapLoaded) return;

    const updateSource = (id: string, data: GeoJSON.FeatureCollection | GeoJSON.Feature | Record<string, unknown>) => {
      const source = map.current?.getSource(id) as maplibregl.GeoJSONSource;
      if (source && data) {
        source.setData(data as GeoJSON.GeoJSON);
      }
    };

    updateSource('vessel-route', routeGeoJSON || { type: 'FeatureCollection', features: [] });
    updateSource('icebergs', icebergsGeoJSON || { type: 'FeatureCollection', features: [] });
    updateSource('risk-map', riskMapGeoJSON || { type: 'FeatureCollection', features: [] });
  }, [routeGeoJSON, icebergsGeoJSON, riskMapGeoJSON, mapLoaded]);

  return (
    <div
      ref={mapContainer}
      className="w-full h-full min-h-[20rem] bg-gray-900 rounded-lg overflow-hidden"
    />
  );
}
