'use client';

import { useState } from 'react';
import Link from 'next/link';
import { useTranslations } from 'next-intl';
import { AlertTriangle, ArrowUpRight, CheckCircle2, Clock, Sparkles } from 'lucide-react';
import { Badge } from '@/components/primitives/badge';
import { cn } from '@/lib/utils/classnameUtils';
import type { SkillHealthItem } from '@/services/statistics';

const STATUS_VARIANT: Record<string, string> = {
  STAR: 'bg-amber-500/15 text-amber-700 dark:text-amber-300 border-amber-500/30',
  HEALTHY: 'bg-emerald-500/15 text-emerald-700 dark:text-emerald-300 border-emerald-500/30',
  AT_RISK: 'bg-red-500/15 text-red-700 dark:text-red-300 border-red-500/30',
  STALE: 'bg-muted text-muted-foreground border-border',
};

function getStatusIcon(status: string) {
  switch (status) {
    case 'STAR':
      return <Sparkles className="h-3.5 w-3.5 text-amber-500 shrink-0" />;
    case 'HEALTHY':
      return <CheckCircle2 className="h-3.5 w-3.5 text-emerald-500 shrink-0" />;
    case 'AT_RISK':
      return <AlertTriangle className="h-3.5 w-3.5 text-destructive shrink-0" />;
    case 'STALE':
    default:
      return <Clock className="h-3.5 w-3.5 text-muted-foreground shrink-0" />;
  }
}

interface SkillHealthPanelProps {
  items: SkillHealthItem[];
}

type TabType = 'all' | 'attention' | 'healthy';

export default function SkillHealthPanel({ items }: SkillHealthPanelProps) {
  const t = useTranslations('growthDashboard.skillHealth');
  const [activeTab, setActiveTab] = useState<TabType>('all');

  if (items.length === 0) {
    return <p className="text-sm text-muted-foreground py-2">{t('empty')}</p>;
  }

  const attentionItems = items.filter((item) => item.status === 'AT_RISK' || item.status === 'STALE');
  const healthyItems = items.filter((item) => item.status === 'STAR' || item.status === 'HEALTHY');

  const filteredItems =
    activeTab === 'attention' ? attentionItems : activeTab === 'healthy' ? healthyItems : items;

  const displayItems = filteredItems.slice(0, 10);

  return (
    <div className="space-y-3">
      {/* Tab Filter Header */}
      <div className="flex items-center gap-1.5 border-b border-border/40 pb-2">
        <button
          type="button"
          onClick={() => setActiveTab('all')}
          className={cn(
            'px-2.5 py-1 text-xs font-medium rounded-md transition-colors',
            activeTab === 'all'
              ? 'bg-muted text-foreground'
              : 'text-muted-foreground hover:text-foreground hover:bg-muted/50',
          )}
        >
          {t('filterAll')} ({items.length})
        </button>
        <button
          type="button"
          onClick={() => setActiveTab('attention')}
          className={cn(
            'px-2.5 py-1 text-xs font-medium rounded-md transition-colors flex items-center gap-1.5',
            activeTab === 'attention'
              ? 'bg-muted text-foreground'
              : 'text-muted-foreground hover:text-foreground hover:bg-muted/50',
          )}
        >
          <span>{t('filterAttention')}</span>
          {attentionItems.length > 0 && (
            <span className="px-1.5 py-0.5 rounded-full text-[10px] font-semibold bg-destructive/15 text-destructive border border-destructive/20">
              {attentionItems.length}
            </span>
          )}
        </button>
        <button
          type="button"
          onClick={() => setActiveTab('healthy')}
          className={cn(
            'px-2.5 py-1 text-xs font-medium rounded-md transition-colors',
            activeTab === 'healthy'
              ? 'bg-muted text-foreground'
              : 'text-muted-foreground hover:text-foreground hover:bg-muted/50',
          )}
        >
          {t('filterHealthy')} ({healthyItems.length})
        </button>
      </div>

      {displayItems.length === 0 ? (
        <p className="text-xs text-muted-foreground py-4 text-center">
          {activeTab === 'attention' ? t('noAttentionNeeded') : t('empty')}
        </p>
      ) : (
        <div className="space-y-2.5">
          {displayItems.map((item) => {
            const isAttention = item.status === 'AT_RISK' || item.status === 'STALE';
            return (
              <div
                key={item.skill_name}
                className={cn(
                  'rounded-lg border px-3 py-2.5 transition-colors',
                  isAttention
                    ? 'border-border/80 bg-muted/20 dark:bg-muted/10'
                    : 'border-border/60 bg-card',
                )}
              >
                <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2">
                  <div className="min-w-0">
                    <div className="flex items-center gap-1.5">
                      {getStatusIcon(item.status)}
                      <p className="text-sm font-medium truncate">{item.skill_name}</p>
                    </div>
                    <p className="text-xs text-muted-foreground mt-0.5">
                      {t('calls7d', { count: item.call_count_7d })}
                      {' · '}
                      {t('callsTotal', { count: item.call_count_total })}
                      {' · '}
                      {t('successRate', { rate: Math.round(item.success_rate_7d * 100) })}
                    </p>
                  </div>
                  <div className="flex items-center gap-2 shrink-0">
                    <span className="text-sm font-semibold tabular-nums">{Math.round(item.health_score)}</span>
                    <Badge
                      variant="outline"
                      className={cn('text-xs flex items-center gap-1', STATUS_VARIANT[item.status] ?? STATUS_VARIANT.STALE)}
                    >
                      {t(`status.${item.status}`, { default: item.status })}
                    </Badge>
                  </div>
                </div>

                {item.actionable_recommendation && (
                  <div className="mt-2 pt-2 border-t border-border/30 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 text-xs">
                    <div className="text-muted-foreground leading-relaxed flex items-start gap-1.5">
                      <span className="font-medium text-foreground/80 shrink-0">{t('recommendationPrefix')}</span>
                      <span>{item.actionable_recommendation}</span>
                    </div>
                    <Link
                      href="/settings/skills"
                      className="inline-flex items-center gap-1 text-[11px] font-medium text-primary hover:underline shrink-0 self-start sm:self-auto"
                    >
                      <span>{t('manageSkill')}</span>
                      <ArrowUpRight className="h-3 w-3" />
                    </Link>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
