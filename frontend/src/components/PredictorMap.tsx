'use client';

import React, { useState, useEffect, useRef } from 'react';
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

// Web-mercator ground resolution at zoom 0 (512 px tiles), metres per pixel at the equator.
const METERS_PER_PIXEL_Z0 = 40075016.686 / 512;

interface PredictorMapProps {
  trajectoryGeoJSON?: GeoJSON.FeatureCollection;
  selectedHorizon: number; // 0, 6, 12, 18, 24, 48, 72
}

export default function PredictorMap({ trajectoryGeoJSON, selectedHorizon }: PredictorMapProps) {
  const mapContainer = useRef<HTMLDivElement>(null);
  const map = useRef<maplibregl.Map | null>(null);
  const [mapLoaded, setMapLoaded] = useState(false);

  useEffect(() => {
    if (map.current || !mapContainer.current) return;

    map.current = new maplibregl.Map({
      container: mapContainer.current,
      style: 'https://demotiles.maplibre.org/style.json',
      center: [0, -90],
      zoom: 2,
      pitch: 45,
      // @ts-expect-error: projection globe is supported in newer maplibre versions
      projection: { type: 'globe' },
    });

    map.current.addControl(new maplibregl.NavigationControl(), 'top-right');
    // Scale bars: kilometres and nautical miles (the unit used for navigation and USNIC sizes).
    map.current.addControl(new maplibregl.ScaleControl({ maxWidth: 120, unit: 'metric' }), 'bottom-left');
    map.current.addControl(new maplibregl.ScaleControl({ maxWidth: 120, unit: 'nautical' }), 'bottom-left');

    map.current.on('load', () => {
      // Source for lines
      map.current!.addSource('trajectories', {
        type: 'geojson',
        data: { type: 'FeatureCollection', features: [] }
      });
      
      // Source for current points at selected horizon
      map.current!.addSource('current-points', {
        type: 'geojson',
        data: { type: 'FeatureCollection', features: [] }
      });

      // Layer for full predicted paths
      map.current!.addLayer({
        id: 'trajectory-lines',
        type: 'line',
        source: 'trajectories',
        layout: {
          'line-join': 'round',
          'line-cap': 'round'
        },
        paint: {
          'line-color': '#3b82f6',
          'line-width': 2,
          'line-dasharray': [2, 2],
          'line-opacity': 0.5
        }
      });

      // Layer for icebergs at the specific time horizon
      map.current!.addLayer({
        id: 'iceberg-points',
        type: 'circle',
        source: 'current-points',
        paint: {
          'circle-radius': 6,
          'circle-color': '#60a5fa',
          'circle-stroke-width': 2,
          'circle-stroke-color': '#ffffff'
        }
      });
      
      // Add halo for uncertainty
      map.current!.addLayer({
        id: 'iceberg-uncertainty',
        type: 'circle',
        source: 'current-points',
        paint: {
          // Radius is a ground distance: scale the zoom-0 pixel radius by 2^zoom.
          'circle-radius': [
            'interpolate', ['exponential', 2], ['zoom'],
            0, ['get', 'uncertainty_px_z0'],
            22, ['*', ['get', 'uncertainty_px_z0'], 4194304]
          ],
          'circle-color': '#60a5fa',
          'circle-opacity': 0.2,
          'circle-pitch-alignment': 'map'
        }
      }, 'iceberg-points');

      const popup = new maplibregl.Popup({
        closeButton: false,
        closeOnClick: false,
        className: 'iceberg-popup'
      });

      map.current!.on('mouseenter', 'iceberg-points', (e) => {
        map.current!.getCanvas().style.cursor = 'pointer';
        if (e.features && e.features[0] && e.features[0].geometry.type === 'Point') {
          const coordinates = e.features[0].geometry.coordinates.slice();
          const props = e.features[0].properties;
          const name = props?.Iceberg || props?.iceberg_id || 'Unknown';
          
          while (Math.abs(e.lngLat.lng - coordinates[0]) > 180) {
            coordinates[0] += e.lngLat.lng > coordinates[0] ? 360 : -360;
          }
          
          popup.setLngLat([coordinates[0], coordinates[1]])
            .setDOMContent(popupLabel(`Iceberg ${name}`))
            .addTo(map.current!);
        }
      });

      map.current!.on('mouseleave', 'iceberg-points', () => {
        map.current!.getCanvas().style.cursor = '';
        popup.remove();
      });

      setMapLoaded(true);
    });
  }, []);

  // Update data when trajectoryGeoJSON, selectedHorizon, or mapLoaded changes
  useEffect(() => {
    if (!map.current || !trajectoryGeoJSON || !mapLoaded) return;

    const sourceTraj = map.current.getSource('trajectories') as maplibregl.GeoJSONSource;
    if (sourceTraj) {
      sourceTraj.setData(trajectoryGeoJSON as GeoJSON.GeoJSON);
    }

    // Extract the point for the selected horizon
    const points: GeoJSON.Feature[] = [];
    
    trajectoryGeoJSON.features.forEach(f => {
      if (f.geometry.type === 'LineString' && f.properties && f.properties.horizons) {
        const idx = (f.properties.horizons as number[]).indexOf(selectedHorizon);
        if (idx !== -1) {
          const coords = f.geometry.coordinates[idx];
          const unc = f.properties.uncertainties[idx];
          const metersPerPixel = METERS_PER_PIXEL_Z0 * Math.cos((coords[1] * Math.PI) / 180);
          points.push({
            type: 'Feature',
            geometry: { type: 'Point', coordinates: coords },
            properties: {
              ...f.properties,
              uncertainty_km: unc,
              uncertainty_px_z0: (unc * 1000) / metersPerPixel
            }
          });
        }
      }
    });

    const sourcePoints = map.current.getSource('current-points') as maplibregl.GeoJSONSource;
    if (sourcePoints) {
      sourcePoints.setData({ type: 'FeatureCollection', features: points } as GeoJSON.GeoJSON);
    }

  }, [trajectoryGeoJSON, selectedHorizon, mapLoaded]);

  return (
    <div
      ref={mapContainer}
      className="w-full h-full min-h-[20rem] bg-gray-900 rounded-lg overflow-hidden"
    />
  );
}
