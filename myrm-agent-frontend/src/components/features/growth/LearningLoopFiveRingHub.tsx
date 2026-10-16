'use client';

/**
 * [INPUT]
 * - @/services/statistics::getLearningLoopStatus, type LearningLoopFiveRingStatusResponse (POS: 闭环学习五环状态服务与契约)
 * - @/components/primitives/card::Card, CardContent, CardHeader, CardTitle (POS: 基础卡片原语)
 * - @/components/primitives/button::Button (POS: 基础按钮原语)
 *
 * [OUTPUT]
 * - LearningLoopFiveRingHub: 五环闭环状态中心组件，呈现战后自省、技能提炼、施用自进、周期自警、渐构画像 5 环的真实计数；来源不可读的环显示「暂不可用」。
 *
 * [POS]
 * 成长与进化仪表盘核心组件。在 /journey 页面以五环拓扑透出 Agent 自进化的真实计数，不做综合评分。
 */

import { memo, useCallback, useEffect, useState } from 'react';
import { useTranslations } from 'next-intl';
import { Brain, Zap, ShieldCheck, RotateCcw, Search, Activity, ArrowRight, RefreshCw } from 'lucide-react';
import { Button } from '@/components/primitives/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/primitives/card';
import { cn } from '@/lib/utils/classnameUtils';
import { getLearningLoopStatus, type LearningLoopFiveRingStatusResponse } from '@/services/statistics';
import { showApiError } from '@/lib/api';

/** Lookback window for the session counter of ring 1; the label shows the same value. */
const LEARNING_LOOP_WINDOW_DAYS = 30;

interface LearningLoopFiveRingHubProps {
  onNavigateTab?: (tab: string) => void;
  className?: string;
}

export const LearningLoopFiveRingHub = memo(function LearningLoopFiveRingHub({
  onNavigateTab,
  className,
}: LearningLoopFiveRingHubProps) {
  const t = useTranslations('growthDashboard.learningLoop');
  const [data, setData] = useState<LearningLoopFiveRingStatusResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const fetchStatus = useCallback(async () => {
    try {
      const res = await getLearningLoopStatus(LEARNING_LOOP_WINDOW_DAYS);
      setData(res);
    } catch (err) {
      showApiError(err);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    fetchStatus();
  }, [fetchStatus]);

  const handleRefresh = useCallback(() => {
    setRefreshing(true);
    fetchStatus();
  }, [fetchStatus]);

  if (loading && !data) {
    return (
      <Card className={cn('p-6 animate-pulse bg-muted/20 border-border/60', className)}>
        <div className="h-6 w-48 bg-muted rounded mb-4" />
        <div className="grid grid-cols-1 md:grid-cols-5 gap-3">
          {[1, 2, 3, 4, 5].map((i) => (
            <div key={i} className="h-32 bg-muted/40 rounded-xl" />
          ))}
        </div>
      </Card>
    );
  }

  if (!data) {
    return null;
  }

  const {
    ring1_reflection: reflection,
    ring2_distillation: distillation,
    ring3_advancement: advancement,
    ring4_consolidation: consolidation,
    ring5_profiling: profiling,
  } = data;

  // A ring whose source could not be read has no metrics and renders as unavailable.
  const rings = [
    {
      id: 'ring1',
      num: '01',
      name: t('ring1.name'),
      stage: t('ring1.stage'),
      desc: t('ring1.desc'),
      icon: Activity,
      color: 'text-amber-500',
      bgColor: 'bg-amber-500/10',
      borderColor: 'border-amber-500/30',
      metrics: reflection
        ? [
            t('ring1.metricsSessions', {
              count: reflection.sessions_in_window,
              days: LEARNING_LOOP_WINDOW_DAYS,
            }),
          ]
        : null,
      targetTab: 'evolution',
    },
    {
      id: 'ring2',
      num: '02',
      name: t('ring2.name'),
      stage: t('ring2.stage'),
      desc: t('ring2.desc'),
      icon: Zap,
      color: 'text-sky-500',
      bgColor: 'bg-sky-500/10',
      borderColor: 'border-sky-500/30',
      metrics: distillation
        ? [
            t('ring2.metricsCases', { count: distillation.cases_total }),
            t('ring2.metricsAutoApplied', { count: distillation.cases_auto_applied }),
          ]
        : null,
      targetTab: 'trends',
    },
    {
      id: 'ring3',
      num: '03',
      name: t('ring3.name'),
      stage: t('ring3.stage'),
      desc: t('ring3.desc'),
      icon: ShieldCheck,
      color: 'text-emerald-500',
      bgColor: 'bg-emerald-500/10',
      borderColor: 'border-emerald-500/30',
      metrics: advancement
        ? [
            t('ring3.metricsPending', { count: advancement.cases_pending_review }),
            t('ring3.metricsBlocked', { count: advancement.cases_blocked }),
          ]
        : null,
      targetTab: 'trends',
    },
    {
      id: 'ring4',
      num: '04',
      name: t('ring4.name'),
      stage: t('ring4.stage'),
      desc: t('ring4.desc'),
      icon: RotateCcw,
      color: 'text-indigo-500',
      bgColor: 'bg-indigo-500/10',
      borderColor: 'border-indigo-500/30',
      metrics: consolidation ? [t('ring4.metricsMemories', { count: consolidation.total_memories })] : null,
      targetTab: 'timeline',
    },
    {
      id: 'ring5',
      num: '05',
      name: t('ring5.name'),
      stage: t('ring5.stage'),
      desc: t('ring5.desc'),
      icon: Search,
      color: 'text-purple-500',
      bgColor: 'bg-purple-500/10',
      borderColor: 'border-purple-500/30',
      metrics: profiling
        ? [
            t('ring5.metricsConversations', { count: profiling.conversations }),
            t('ring5.metricsProfile', { count: profiling.profile_entries }),
          ]
        : null,
      targetTab: 'graph',
    },
  ];

  return (
    <Card
      className={cn(
        'relative overflow-hidden border-border/70 bg-gradient-to-b from-card/90 to-card/60 shadow-sm backdrop-blur-sm',
        className,
      )}
    >
      <CardHeader className="pb-3 pt-4 px-4 md:px-6">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
          <div className="space-y-1">
            <div className="flex items-center gap-2">
              <div className="p-1.5 rounded-lg bg-primary/10 text-primary">
                <Brain className="h-5 w-5" />
              </div>
              <CardTitle className="text-base md:text-lg font-semibold tracking-tight">{t('title')}</CardTitle>
            </div>
            <p className="text-xs text-muted-foreground">{t('subtitle')}</p>
          </div>

          <Button
            variant="outline"
            size="sm"
            onClick={handleRefresh}
            disabled={refreshing}
            className="h-8 px-2.5 text-xs self-start sm:self-auto"
          >
            <RefreshCw className={cn('h-3.5 w-3.5 mr-1', refreshing && 'animate-spin')} />
            <span className="sr-only sm:not-sr-only">{t('refresh')}</span>
          </Button>
        </div>
      </CardHeader>

      <CardContent className="px-4 pb-5 md:px-6">
        {/* Five Rings Topology Grid */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-3 relative">
          {rings.map((ring) => {
            const Icon = ring.icon;
            return (
              <button
                key={ring.id}
                type="button"
                onClick={() => onNavigateTab?.(ring.targetTab)}
                className={cn(
                  'group relative flex flex-col justify-between p-3.5 rounded-xl border text-start transition-all duration-200 cursor-pointer',
                  'bg-background/60 hover:bg-accent/40 hover:shadow-md hover:border-primary/40',
                  ring.borderColor,
                )}
              >
                <span>
                  <span className="flex items-center justify-between mb-2">
                    <span className="text-[10px] font-mono font-semibold text-muted-foreground/80 px-1.5 py-0.5 rounded bg-muted/60">
                      {ring.num}
                    </span>
                    <span className={cn('p-1.5 rounded-lg shrink-0', ring.bgColor, ring.color)}>
                      <Icon className="h-4 w-4" />
                    </span>
                  </span>

                  <span className="text-sm font-semibold text-foreground group-hover:text-primary transition-colors flex items-center justify-between">
                    <span>{ring.name}</span>
                    <ArrowRight className="h-3 w-3 opacity-0 -translate-x-1 group-hover:opacity-100 group-hover:translate-x-0 transition-all text-primary" />
                  </span>
                  <span className="block text-[11px] font-medium text-muted-foreground mt-0.5">{ring.stage}</span>
                  <span className="block text-[11px] text-muted-foreground/75 mt-1.5 leading-relaxed">{ring.desc}</span>
                </span>

                <span className="mt-3 pt-2.5 border-t border-border/40 space-y-1">
                  {ring.metrics ? (
                    ring.metrics.map((metric) => (
                      <span key={metric} className="block text-[11px] text-foreground/90 font-medium">
                        {metric}
                      </span>
                    ))
                  ) : (
                    <span className="block text-[11px] text-muted-foreground">{t('unavailable')}</span>
                  )}
                </span>
              </button>
            );
          })}
        </div>
      </CardContent>
    </Card>
  );
});

export default LearningLoopFiveRingHub;
