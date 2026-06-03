'use client';

import { useMemo } from 'react';
import { useTranslations } from 'next-intl';
import { RadarChart, PolarGrid, PolarAngleAxis, Radar, ResponsiveContainer } from 'recharts';
import { cn } from '@/lib/utils/classnameUtils';

interface HealthRadarProps {
  dimensions: Record<string, number>;
  score: number;
}

const DIMENSION_KEYS = ['freshness', 'coverage', 'retentionHealth', 'coherence'] as const;
type DimensionKey = (typeof DIMENSION_KEYS)[number];

const DIMENSION_API_MAP: Record<DimensionKey, string> = {
  freshness: 'freshness',
  coverage: 'coverage',
  retentionHealth: 'retention_health',
  coherence: 'coherence',
};

export default function HealthRadar({ dimensions, score }: HealthRadarProps) {
  const t = useTranslations('growthDashboard.healthRadar');

  const chartData = useMemo(() => {
    return DIMENSION_KEYS.filter((k) => {
      const apiKey = DIMENSION_API_MAP[k];
      return apiKey in dimensions;
    }).map((key) => {
      const apiKey = DIMENSION_API_MAP[key];
      return {
        label: t(key),
        value: Math.round((dimensions[apiKey] ?? 0) * 100),
      };
    });
  }, [dimensions, t]);

  const scoreColor = score >= 70 ? 'text-emerald-500' : score >= 40 ? 'text-amber-500' : 'text-red-500';

  if (chartData.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-48 text-muted-foreground text-sm">
        <span className={cn('text-4xl font-bold mb-1', scoreColor)}>{score}</span>
        <span className="text-xs">/100</span>
      </div>
    );
  }

  return (
    <div className="relative">
      <ResponsiveContainer width="100%" height={220}>
        <RadarChart data={chartData} cx="50%" cy="50%" outerRadius="70%">
          <PolarGrid stroke="hsl(var(--border))" />
          <PolarAngleAxis dataKey="label" tick={{ fill: 'hsl(var(--muted-foreground))', fontSize: 11 }} />
          <Radar
            dataKey="value"
            stroke="hsl(var(--primary))"
            fill="hsl(var(--primary))"
            fillOpacity={0.2}
            strokeWidth={2}
          />
        </RadarChart>
      </ResponsiveContainer>

      {/* Center score overlay */}
      <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
        <div className="text-center">
          <span className={cn('text-2xl font-bold', scoreColor)}>{score}</span>
        </div>
      </div>
    </div>
  );
}
