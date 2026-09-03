'use client';

import React from 'react';
import { useTranslations } from 'next-intl';
import { ArrowUpRight, Cpu, Layers, ShieldAlert, Sparkles, Terminal, Wrench } from 'lucide-react';
import type { AblationRecommendationItem } from '../hooks/useCasesEval';

interface ComponentAblationImpactRankingChipProps {
  recommendations: AblationRecommendationItem[];
  profileId?: string;
}

export function ComponentAblationImpactRankingChip({
  recommendations,
  profileId,
}: ComponentAblationImpactRankingChipProps) {
  const t = useTranslations('evalLab.ablation');

  if (!recommendations || recommendations.length === 0) {
    return null;
  }

  const getTierIcon = (component: string) => {
    switch (component) {
      case 'tool':
        return <Wrench className="w-4 h-4 text-emerald-500" />;
      case 'middleware':
        return <Layers className="w-4 h-4 text-blue-500" />;
      case 'memory':
        return <Cpu className="w-4 h-4 text-purple-500" />;
      case 'prompt':
        return <Terminal className="w-4 h-4 text-amber-500" />;
      default:
        return <Sparkles className="w-4 h-4 text-primary" />;
    }
  };

  const getTierStars = (priority: number) => {
    switch (priority) {
      case 1:
        return '★★★★★ (Highest ROI)';
      case 2:
        return '★★★★☆ (High ROI)';
      case 3:
        return '★★★☆☆ (Medium ROI)';
      case 4:
      default:
        return '★★☆☆☆ (Low ROI)';
    }
  };

  const handleNavigate = (tab: string, settingKey: string) => {
    if (typeof window === 'undefined') return;
    const targetAgentId = profileId || '';
    const searchParams = new URLSearchParams();
    if (targetAgentId) searchParams.set('agentId', targetAgentId);
    searchParams.set('tab', tab);
    searchParams.set('highlight', settingKey);
    window.location.href = `/settings#${tab}?${searchParams.toString()}`;
  };

  return (
    <div className="border border-border/80 rounded-xl p-4 bg-muted/20 space-y-3">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Sparkles className="w-5 h-5 text-primary" />
          <h4 className="text-sm font-semibold tracking-tight">{t('title')}</h4>
        </div>
        <span className="text-xs text-muted-foreground font-mono">{t('subtitle')}</span>
      </div>

      <p className="text-xs text-muted-foreground leading-relaxed">{t('description')}</p>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-3 pt-1">
        {recommendations.map((rec) => (
          <div
            key={rec.action_key}
            className="flex flex-col justify-between p-3 rounded-lg border border-border/60 bg-card hover:bg-muted/30 transition-colors gap-2"
          >
            <div className="space-y-1.5">
              <div className="flex items-center justify-between gap-2">
                <div className="flex items-center gap-1.5">
                  {getTierIcon(rec.component)}
                  <span className="text-xs font-semibold capitalize tracking-wide">{rec.component}</span>
                  <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-muted text-muted-foreground">
                    Tier {rec.priority}
                  </span>
                </div>
                <span className="text-[10px] text-amber-500 font-mono font-medium">{getTierStars(rec.priority)}</span>
              </div>

              <h5 className="text-xs font-medium text-foreground">{rec.title}</h5>
              <p className="text-xs text-muted-foreground leading-normal">{rec.reason}</p>
            </div>

            <div className="flex items-center justify-between pt-1 border-t border-border/40 mt-1">
              <span className="text-[11px] text-muted-foreground font-mono">
                {t('affectsCases', { count: rec.affected_case_count })}
              </span>

              <button
                type="button"
                onClick={() => handleNavigate(rec.target_config_tab, rec.target_setting_key)}
                className="inline-flex items-center gap-1 text-xs font-medium text-primary hover:underline hover:opacity-90 transition-opacity"
              >
                <span>{t('quickConfig')}</span>
                <ArrowUpRight className="w-3.5 h-3.5" />
              </button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

export default ComponentAblationImpactRankingChip;
