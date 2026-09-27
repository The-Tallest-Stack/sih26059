'use client';

import React from 'react';
import { DataFreshness } from '../lib/types';

interface DataFreshnessBarProps {
  sources: DataFreshness[];
}

const getStatusColor = (ageMinutes: number) => {
  if (ageMinutes < 60) return 'bg-green-500'; // < 1h
  if (ageMinutes < 360) return 'bg-yellow-500'; // < 6h
  return 'bg-red-500'; // > 6h
};

export default function DataFreshnessBar({ sources }: DataFreshnessBarProps) {
  if (!sources || sources.length === 0) return null;

  return (
    <div className="fixed bottom-0 left-0 right-0 bg-gray-900 border-t border-gray-800 text-white p-2 text-xs z-50">
      <div className="flex flex-wrap justify-center gap-6 max-w-7xl mx-auto">
        {sources.map((source, idx) => (
          <div key={idx} className="flex items-center space-x-2">
            <span className="font-semibold text-gray-400">{source.source}:</span>
            <div className="flex items-center">
              <div className={`w-2 h-2 rounded-full mr-2 ${getStatusColor(source.ageMinutes)}`} />
              <span>{source.ageMinutes}m ago</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
