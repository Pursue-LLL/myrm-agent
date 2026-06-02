'use client';

import React, { useEffect, useState } from 'react';
import { getInsightsSummary, type InsightsSummary } from '@/services/skill-optimization';
import { useTranslations } from 'next-intl';

export function InsightsDashboard() {
  const t = useTranslations('SkillOptimization');
  const [data, setData] = useState<InsightsSummary | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let mounted = true;
    getInsightsSummary(7)
      .then((summary) => {
        if (mounted) setData(summary);
      })
      .catch(console.error)
      .finally(() => {
        if (mounted) setLoading(false);
      });
    return () => {
      mounted = false;
    };
  }, []);

  if (loading) {
    return <div className="flex h-32 items-center justify-center">{t('loading')}</div>;
  }

  if (!data) {
    return <div className="flex h-32 items-center justify-center text-muted-foreground">{t('noData')}</div>;
  }

  return (
    <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
      <div className="flex flex-col rounded-lg border bg-card p-4">
        <span className="text-sm text-muted-foreground">{t('activeSkills')}</span>
        <span className="text-2xl font-bold">{data.summary.active_skills}</span>
      </div>
      <div className="flex flex-col rounded-lg border bg-card p-4">
        <span className="text-sm text-muted-foreground">{t('totalCalls')}</span>
        <span className="text-2xl font-bold">{data.summary.total_calls}</span>
      </div>
      <div className="flex flex-col rounded-lg border bg-card p-4">
        <span className="text-sm text-muted-foreground">{t('avgSuccessRate')}</span>
        <span className="text-2xl font-bold">{(data.summary.success_rate * 100).toFixed(1)}%</span>
      </div>
      <div className="flex flex-col rounded-lg border bg-card p-4">
        <span className="text-sm text-muted-foreground">{t('avgExecutionTime')}</span>
        <span className="text-2xl font-bold">{data.summary.avg_duration_seconds.toFixed(2)}s</span>
      </div>
    </div>
  );
}
