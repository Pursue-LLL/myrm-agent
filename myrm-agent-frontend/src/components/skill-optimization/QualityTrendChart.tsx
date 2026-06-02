'use client';

import React, { useEffect, useState } from 'react';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';
import { getSkillQualityHistory } from '@/services/skill-optimization';
import { useTranslations } from 'next-intl';

interface QualityTrendChartProps {
  skillId: string;
  days?: number;
  className?: string;
}

export function QualityTrendChart({ skillId, days = 30, className = 'h-64 w-full' }: QualityTrendChartProps) {
  const t = useTranslations('SkillOptimization');
  const [data, setData] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let mounted = true;
    getSkillQualityHistory(skillId, days)
      .then((history) => {
        if (mounted) {
          const chartData = history.map((point) => ({
            date: new Date(point.timestamp).toLocaleDateString(),
            score: point.quality_score.overall_score * 100,
            success: point.quality_score.success_rate * 100,
          }));
          setData(chartData);
        }
      })
      .catch(console.error)
      .finally(() => {
        if (mounted) setLoading(false);
      });
    return () => {
      mounted = false;
    };
  }, [skillId, days]);

  if (loading) {
    return <div className="flex h-64 items-center justify-center">{t('loading')}</div>;
  }

  if (data.length === 0) {
    return <div className="flex h-64 items-center justify-center text-muted-foreground">{t('noData')}</div>;
  }

  return (
    <div className={className}>
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 5, right: 20, left: 0, bottom: 5 }}>
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis dataKey="date" className="text-xs" />
          <YAxis domain={[0, 100]} className="text-xs" />
          <Tooltip />
          <Legend />
          <Line type="monotone" name={t('overallScore')} dataKey="score" stroke="#8884d8" activeDot={{ r: 8 }} />
          <Line type="monotone" name={t('successRate')} dataKey="success" stroke="#82ca9d" />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
