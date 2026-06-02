'use client';

import React, { useEffect, useState } from 'react';
import { useTranslations } from 'next-intl';

interface GlobalBaseline {
  skill_id: string;
  global_avg_score: number;
  recommended_version: string;
  improvement_over_baseline: number;
}

export function GlobalAwarenessUI({ skillId }: { skillId: string }) {
  const t = useTranslations('SkillOptimization');
  const [baseline, setBaseline] = useState<GlobalBaseline | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    // 模拟从 Server 获取全局基线数据
    // Server 会定期从 Control Plane 拉取
    let mounted = true;
    setTimeout(() => {
      if (mounted) {
        if (skillId === 'web_search') {
          setBaseline({
            skill_id: 'web_search',
            global_avg_score: 0.92,
            recommended_version: 'v2.1',
            improvement_over_baseline: 0.15,
          });
        }
        setLoading(false);
      }
    }, 500);
    return () => {
      mounted = false;
    };
  }, [skillId]);

  if (loading) return <div className="animate-pulse h-16 bg-muted rounded-full" />;
  if (!baseline) return null;

  return (
    <div className="flex items-center justify-between p-4 border rounded-lg bg-blue-50/50 dark:bg-blue-950/20 border-blue-200 dark:border-blue-900">
      <div className="flex flex-col gap-1">
        <h4 className="font-semibold text-blue-800 dark:text-blue-300">
          {t('communityRecommendation') || 'Community Recommendation'}
        </h4>
        <p className="text-sm text-blue-600 dark:text-blue-400">
          Global Avg Score: {(baseline.global_avg_score * 100).toFixed(1)}% (↑{' '}
          {(baseline.improvement_over_baseline * 100).toFixed(1)}%)
        </p>
        <p className="text-xs text-muted-foreground">
          Version {baseline.recommended_version} is performing better globally.
        </p>
      </div>
      <button className="px-4 py-2 text-sm font-medium text-white bg-blue-600 rounded-full hover:bg-blue-700">
        {t('upgradeToRecommended') || 'Upgrade to Recommended'}
      </button>
    </div>
  );
}
