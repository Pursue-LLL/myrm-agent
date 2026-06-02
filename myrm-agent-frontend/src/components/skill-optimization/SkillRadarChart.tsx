'use client';

import React from 'react';
import { Radar, RadarChart, PolarGrid, PolarAngleAxis, PolarRadiusAxis, ResponsiveContainer, Tooltip } from 'recharts';
import type { SkillQualityScore } from '@/services/skill-optimization';
import { useTranslations } from 'next-intl';

interface SkillRadarChartProps {
  score: SkillQualityScore;
  className?: string;
}

export function SkillRadarChart({ score, className = 'h-64 w-full' }: SkillRadarChartProps) {
  const t = useTranslations('SkillOptimization');

  const data = [
    { subject: t('successRate'), A: score.success_rate * 100, fullMark: 100 },
    { subject: t('tokenEfficiency'), A: score.token_efficiency * 100, fullMark: 100 },
    { subject: t('executionTime'), A: score.execution_time * 100, fullMark: 100 },
    { subject: t('userSatisfaction'), A: score.user_satisfaction * 100, fullMark: 100 },
    { subject: t('callFrequency'), A: score.call_frequency * 100, fullMark: 100 },
  ];

  return (
    <div className={className}>
      <ResponsiveContainer width="100%" height="100%">
        <RadarChart cx="50%" cy="50%" outerRadius="80%" data={data}>
          <PolarGrid />
          <PolarAngleAxis dataKey="subject" className="text-xs" />
          <PolarRadiusAxis angle={30} domain={[0, 100]} />
          <Radar name={t('qualityScore')} dataKey="A" stroke="#8884d8" fill="#8884d8" fillOpacity={0.6} />
          <Tooltip />
        </RadarChart>
      </ResponsiveContainer>
    </div>
  );
}
