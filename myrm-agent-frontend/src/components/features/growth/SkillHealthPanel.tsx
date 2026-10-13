/**
 * [INPUT]
 * - next-intl::useTranslations (POS: 前端国际化 Hook)
 * - @/services/statistics::SkillHealthItem (POS: 技能健康度与治理建议契约)
 * - @/components/primitives/badge::Badge (POS: 语义化徽章组件)
 *
 * [OUTPUT]
 * - SkillHealthPanel: 技能健康度与周复盘治理面板，支持全量/待治理/健康分段筛选与自愈动作指引
 *
 * [POS]
 * 成长进化中心技能健康度组件。解决盲目过滤与死特性问题，直观呈现 Harness 纯规则健康分与治理处置建议。
 * 只展示近 7 天有运行的技能；沉睡与归档由技能库（SkillCard）的 Curator 生命周期徽章呈现。
 */
'use client';

import { useState } from 'react';
import Link from 'next/link';
import { useTranslations } from 'next-intl';
import { AlertTriangle, ArrowUpRight, CheckCircle2, CircleDashed, Clock, Sparkles } from 'lucide-react';
import { Badge } from '@/components/primitives/badge';
import { cn } from '@/lib/utils/classnameUtils';
import type { SkillHealthItem } from '@/services/statistics';

const STATUS_VARIANT: Record<string, string> = {
  STAR: 'bg-amber-500/15 text-amber-700 dark:text-amber-300 border-amber-500/30',
  HEALTHY: 'bg-emerald-500/15 text-emerald-700 dark:text-emerald-300 border-emerald-500/30',
  AT_RISK: 'bg-red-500/15 text-red-700 dark:text-red-300 border-red-500/30',
  UNPROVEN: 'bg-sky-500/15 text-sky-700 dark:text-sky-300 border-sky-500/30',
};

/** Badge style of a status this build does not know. */
const NEUTRAL_VARIANT = 'bg-muted text-muted-foreground border-border';

const RECOMMENDATION_KEY: Record<string, string> = {
  STAR: 'recStar',
  HEALTHY: 'recHealthy',
  AT_RISK: 'recAtRisk',
  UNPROVEN: 'recUnproven',
};

function getStatusIcon(status: string) {
  switch (status) {
    case 'STAR':
      return <Sparkles className="h-3.5 w-3.5 text-amber-500 shrink-0" />;
    case 'HEALTHY':
      return <CheckCircle2 className="h-3.5 w-3.5 text-emerald-500 shrink-0" />;
    case 'AT_RISK':
      return <AlertTriangle className="h-3.5 w-3.5 text-destructive shrink-0" />;
    case 'UNPROVEN':
      return <CircleDashed className="h-3.5 w-3.5 text-sky-500 shrink-0" />;
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
  const [isExpanded, setIsExpanded] = useState<boolean>(false);

  if (items.length === 0) {
    return <p className="text-sm text-muted-foreground py-2">{t('empty')}</p>;
  }

  const attentionItems = items.filter((item) => item.status === 'AT_RISK');
  const healthyItems = items.filter((item) => item.status === 'STAR' || item.status === 'HEALTHY');

  const filteredItems = activeTab === 'attention' ? attentionItems : activeTab === 'healthy' ? healthyItems : items;

  const displayItems = isExpanded ? filteredItems : filteredItems.slice(0, 8);

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
            const isAttention = item.status === 'AT_RISK';
            return (
              <div
                key={item.skill_name}
                className={cn(
                  'rounded-lg border px-3 py-2.5 transition-colors',
                  isAttention ? 'border-border/80 bg-muted/20 dark:bg-muted/10' : 'border-border/60 bg-card',
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
                      {item.success_rate_7d !== null && (
                        <>
                          {' · '}
                          {t('successRate', { rate: Math.round(item.success_rate_7d * 100) })}
                        </>
                      )}
                    </p>
                  </div>
                  <div className="flex items-center gap-2 shrink-0">
                    {/* An unproven skill's score only measures how little evidence exists, so it is not shown. */}
                    <span className="text-sm font-semibold tabular-nums">
                      {item.status === 'UNPROVEN' ? '–' : Math.round(item.health_score)}
                    </span>
                    <Badge
                      variant="outline"
                      className={cn(
                        'text-xs flex items-center gap-1',
                        STATUS_VARIANT[item.status] ?? NEUTRAL_VARIANT,
                      )}
                    >
                      {item.status in STATUS_VARIANT ? t(`status.${item.status}`) : item.status}
                    </Badge>
                  </div>
                </div>

                {item.actionable_recommendation && (
                  <div className="mt-2 pt-2 border-t border-border/30 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 text-xs">
                    <div className="text-muted-foreground leading-relaxed flex items-start gap-1.5">
                      <span className="font-medium text-foreground/80 shrink-0">{t('recommendationPrefix')}</span>
                      <span>
                        {item.status in RECOMMENDATION_KEY
                          ? t(RECOMMENDATION_KEY[item.status], {
                              observed: item.observed_count_7d,
                              required: item.min_observed_count,
                            })
                          : item.actionable_recommendation}
                      </span>
                    </div>
                    <Link
                      href={`/settings/skills?search=${encodeURIComponent(item.skill_name)}`}
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

      {filteredItems.length > 8 && (
        <div className="pt-1 text-center">
          <button
            type="button"
            onClick={() => setIsExpanded((prev) => !prev)}
            className="text-xs font-medium text-primary hover:underline transition-colors px-3 py-1 rounded-md hover:bg-muted/40"
          >
            {isExpanded ? t('showLess') : t('showMore', { count: filteredItems.length })}
          </button>
        </div>
      )}
    </div>
  );
}
