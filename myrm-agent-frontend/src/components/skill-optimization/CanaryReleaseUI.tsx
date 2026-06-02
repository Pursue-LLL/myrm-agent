'use client';

import React, { useEffect, useState } from 'react';
import { useTranslations } from 'next-intl';

interface CanaryMetrics {
  baseline_success_rate: number;
  candidate_success_rate: number;
  traffic_ratio: number;
  sample_size: number;
  target_sample_size: number;
}

export function CanaryReleaseUI({ skillId }: { skillId: string }) {
  const t = useTranslations('SkillOptimization');
  const [metrics, setMetrics] = useState<CanaryMetrics | null>(null);

  useEffect(() => {
    // 模拟从 Server 获取灰度发布数据
    let mounted = true;
    setTimeout(() => {
      if (mounted) {
        setMetrics({
          baseline_success_rate: 0.85,
          candidate_success_rate: 0.91,
          traffic_ratio: 0.1,
          sample_size: 450,
          target_sample_size: 1000,
        });
      }
    }, 500);
    return () => {
      mounted = false;
    };
  }, [skillId]);

  if (!metrics) return null;

  return (
    <div className="flex flex-col gap-4 p-4 border rounded-lg bg-card">
      <div className="flex items-center justify-between">
        <h4 className="font-semibold">{t('canaryReleaseStatus') || 'Canary Release Status'}</h4>
        <span className="px-2 py-1 text-xs font-medium text-orange-800 bg-orange-100 rounded-full dark:bg-orange-900/30 dark:text-orange-300">
          Running ({(metrics.traffic_ratio * 100).toFixed(0)}% Traffic)
        </span>
      </div>

      <div className="grid grid-cols-2 gap-4">
        <div className="flex flex-col p-3 border rounded-md">
          <span className="text-sm text-muted-foreground">Baseline (v1.0)</span>
          <span className="text-xl font-bold">{(metrics.baseline_success_rate * 100).toFixed(1)}%</span>
        </div>
        <div className="flex flex-col p-3 border rounded-md border-primary/50 bg-primary/5">
          <span className="text-sm text-muted-foreground">Candidate (v1.1)</span>
          <span className="text-xl font-bold text-primary">{(metrics.candidate_success_rate * 100).toFixed(1)}%</span>
        </div>
      </div>

      <div className="flex flex-col gap-1 mt-2">
        <div className="flex justify-between text-xs text-muted-foreground">
          <span>Progress: {metrics.sample_size} samples</span>
          <span>Target: {metrics.target_sample_size} samples</span>
        </div>
        <div className="w-full h-2 rounded-full bg-secondary overflow-hidden">
          <div
            className="h-full bg-primary transition-all duration-500"
            style={{
              width: `${Math.min(100, (metrics.sample_size / metrics.target_sample_size) * 100)}%`,
            }}
          />
        </div>
      </div>
    </div>
  );
}
