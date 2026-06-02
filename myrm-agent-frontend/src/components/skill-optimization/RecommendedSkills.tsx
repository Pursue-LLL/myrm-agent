'use client';

import React, { useEffect, useState } from 'react';
import {
  getRecommendations,
  triggerBatchOptimization,
  type OptimizationRecommendation,
} from '@/services/skill-optimization';
import { useTranslations } from 'next-intl';

export function RecommendedSkills() {
  const t = useTranslations('SkillOptimization');
  const [recommendations, setRecommendations] = useState<OptimizationRecommendation[]>([]);
  const [loading, setLoading] = useState(true);
  const [optimizing, setOptimizing] = useState<Set<string>>(new Set());

  useEffect(() => {
    let mounted = true;
    getRecommendations(5)
      .then((res) => {
        if (mounted) setRecommendations(res.recommendations);
      })
      .catch(console.error)
      .finally(() => {
        if (mounted) setLoading(false);
      });
    return () => {
      mounted = false;
    };
  }, []);

  const handleOptimize = async (skillId: string) => {
    setOptimizing((prev) => new Set(prev).add(skillId));
    try {
      await triggerBatchOptimization([skillId]);
      // Remove from recommendations after triggered
      setRecommendations((prev) => prev.filter((r) => r.skill_id !== skillId));
    } catch (e) {
      console.error('Failed to trigger optimization', e);
    } finally {
      setOptimizing((prev) => {
        const next = new Set(prev);
        next.delete(skillId);
        return next;
      });
    }
  };

  const handleOptimizeAll = async () => {
    const ids = recommendations.map((r) => r.skill_id);
    setOptimizing(new Set(ids));
    try {
      await triggerBatchOptimization(ids);
      setRecommendations([]);
    } catch (e) {
      console.error('Failed to trigger batch optimization', e);
      setOptimizing(new Set());
    }
  };

  if (loading) {
    return <div className="flex h-32 items-center justify-center">{t('loading')}</div>;
  }

  if (recommendations.length === 0) {
    return <div className="flex h-32 items-center justify-center text-muted-foreground">{t('noRecommendations')}</div>;
  }

  return (
    <div className="flex flex-col gap-4 rounded-lg border bg-card p-4">
      <div className="flex items-center justify-between">
        <h3 className="text-lg font-semibold">{t('recommendedToOptimize')}</h3>
        <button
          onClick={handleOptimizeAll}
          disabled={optimizing.size > 0}
          className="rounded bg-primary px-3 py-1 text-sm text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
        >
          {t('optimizeAll')}
        </button>
      </div>
      <div className="flex flex-col gap-3">
        {recommendations.map((rec) => (
          <div key={rec.skill_id} className="flex items-center justify-between rounded-full border p-3">
            <div className="flex flex-col">
              <span className="font-medium">{rec.skill_name}</span>
              <span className="text-xs text-muted-foreground">
                {t('priorityScore')}: {(rec.priority_score * 100).toFixed(0)} | {rec.reasons[0]}
              </span>
            </div>
            <button
              onClick={() => handleOptimize(rec.skill_id)}
              disabled={optimizing.has(rec.skill_id)}
              className="rounded border px-3 py-1 text-sm hover:bg-accent disabled:opacity-50"
            >
              {optimizing.has(rec.skill_id) ? t('optimizing') : t('optimize')}
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}
