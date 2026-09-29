'use client';

import React from 'react';
import { DataFreshness } from '../lib/types';

interface DataFreshnessBarProps {
  sources: DataFreshness[];
}

const STATUS_COLORS: Record<DataFreshness['status'], string> = {
  fresh: 'bg-green-500',
  stale: 'bg-yellow-500',
  unavailable: 'bg-red-500',
  synthetic: 'bg-purple-500',
};

const formatAge = (minutes: number) => {
  if (minutes < 60) return `${Math.round(minutes)}m ago`;
  if (minutes < 48 * 60) return `${Math.round(minutes / 60)}h ago`;
  return `${Math.round(minutes / (24 * 60))}d ago`;
};

const statusLabel = (source: DataFreshness) => {
  if (source.status === 'unavailable') return 'Unavailable';
  if (source.status === 'synthetic') return 'Synthetic (placeholder)';
  const age = formatAge(source.ageMinutes);
  return source.status === 'stale' ? `Stale, ${age}` : age;
};

export default function DataFreshnessBar({ sources }: DataFreshnessBarProps) {
  if (!sources || sources.length === 0) return null;

  return (
    <div className="flex-shrink-0 bg-gray-900 border border-gray-800 rounded text-white px-2 py-1.5 text-xs">
      <div className="flex flex-wrap justify-center gap-x-6 gap-y-1">
        {sources.map((source) => (
          <div
            key={source.source}
            className="flex items-center space-x-2"
            title={source.lastUpdated ? `Last updated ${new Date(source.lastUpdated).toLocaleString()}` : undefined}
          >
            <span className="font-semibold text-gray-400">{source.source}:</span>
            <div className="flex items-center">
              <div className={`w-2 h-2 rounded-full mr-2 ${STATUS_COLORS[source.status] || 'bg-gray-500'}`} />
              <span>{statusLabel(source)}</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
