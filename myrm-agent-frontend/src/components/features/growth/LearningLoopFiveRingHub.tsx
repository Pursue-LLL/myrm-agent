'use client';

/**
 * [INPUT]
 * - @/services/statistics::getLearningLoopStatus, type LearningLoopFiveRingStatusResponse (POS: 闭环学习五环状态服务与契约)
 * - @/components/primitives/card::Card, CardContent, CardHeader, CardTitle (POS: 基础卡片原语)
 * - @/components/primitives/button::Button (POS: 基础按钮原语)
 *
 * [OUTPUT]
 * - LearningLoopFiveRingHub: 五环闭环状态中心组件，呈现战后自省、技能提炼、施用自进、周期自警、渐构画像 5 环交互拓扑与健康度量。
 *
 * [POS]
 * 成长与进化仪表盘核心组件。在 /journey 页面以流动闭环拓扑与健康指标透出 Agent 自进化全貌。
 */

import { memo, useCallback, useEffect, useState } from 'react';
import { useTranslations } from 'next-intl';
import {
  Brain,
  Sparkles,
  Zap,
  ShieldCheck,
  RotateCcw,
  Search,
  Activity,
  ArrowRight,
  CheckCircle2,
  AlertCircle,
  Clock,
  RefreshCw,
} from 'lucide-react';
import { Button } from '@/components/primitives/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/primitives/card';
import { cn } from '@/lib/utils/classnameUtils';
import { getLearningLoopStatus, type LearningLoopFiveRingStatusResponse } from '@/services/statistics';
import { showApiError } from '@/lib/api';

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
      const res = await getLearningLoopStatus(30);
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
      metrics: [
        t('ring1.metricsTraces', { count: data.ring1_reflection.total_traces_analyzed }),
        t('ring1.metricsAntiPatterns', { count: data.ring1_reflection.anti_patterns_detected }),
      ],
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
      metrics: [
        t('ring2.metricsProposals', { count: data.ring2_distillation.proposals_generated }),
        t('ring2.metricsApproved', { count: data.ring2_distillation.proposals_approved }),
      ],
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
      metrics: [
        t('ring3.metricsEvals', { count: data.ring3_advancement.evaluations_run }),
        t('ring3.metricsBlocked', { count: data.ring3_advancement.regressions_blocked }),
        t('ring3.metricsBoost', { pct: data.ring3_advancement.avg_score_boost_pct.toFixed(0) }),
      ],
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
      metrics: [
        t('ring4.metricsCycles', { count: data.ring4_consolidation.consolidation_cycles }),
        t('ring4.metricsMerged', { count: data.ring4_consolidation.memories_merged }),
        t('ring4.metricsMemories', { count: data.ring4_consolidation.total_memories }),
      ],
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
      metrics: [
        t('ring5.metricsIndexed', { count: data.ring5_profiling.conversations_indexed }),
        t('ring5.metricsDimensions', { count: data.ring5_profiling.profile_dimensions }),
      ],
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
              <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20">
                <CheckCircle2 className="h-3 w-3 mr-1" />
                {t(data.overall_status === 'optimal' ? 'optimal' : 'warning')}
              </span>
            </div>
            <p className="text-xs text-muted-foreground">{t('subtitle')}</p>
          </div>

          <div className="flex items-center gap-3">
            <div className="text-right">
              <p className="text-xs text-muted-foreground font-medium">{t('healthScore')}</p>
              <p className="text-lg md:text-xl font-bold text-foreground">
                {data.overall_loop_health_score}
                <span className="text-xs font-normal text-muted-foreground ml-0.5">/100</span>
              </p>
            </div>
            <Button
              variant="outline"
              size="sm"
              onClick={handleRefresh}
              disabled={refreshing}
              className="h-8 px-2.5 text-xs"
            >
              <RefreshCw className={cn('h-3.5 w-3.5 mr-1', refreshing && 'animate-spin')} />
              <span className="sr-only sm:not-sr-only">刷新</span>
            </Button>
          </div>
        </div>
      </CardHeader>

      <CardContent className="px-4 pb-5 md:px-6">
        {/* Five Rings Topology Grid */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-3 relative">
          {rings.map((ring, idx) => {
            const Icon = ring.icon;
            return (
              <div
                key={ring.id}
                onClick={() => onNavigateTab && onNavigateTab(ring.targetTab)}
                className={cn(
                  'group relative flex flex-col justify-between p-3.5 rounded-xl border transition-all duration-200 cursor-pointer',
                  'bg-background/60 hover:bg-accent/40 hover:shadow-md hover:border-primary/40',
                  ring.borderColor,
                )}
              >
                <div>
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-[10px] font-mono font-semibold text-muted-foreground/80 px-1.5 py-0.5 rounded bg-muted/60">
                      {ring.num}
                    </span>
                    <div className={cn('p-1.5 rounded-lg shrink-0', ring.bgColor, ring.color)}>
                      <Icon className="h-4 w-4" />
                    </div>
                  </div>

                  <h4 className="text-sm font-semibold text-foreground group-hover:text-primary transition-colors flex items-center justify-between">
                    <span>{ring.name}</span>
                    <ArrowRight className="h-3 w-3 opacity-0 -translate-x-1 group-hover:opacity-100 group-hover:translate-x-0 transition-all text-primary" />
                  </h4>
                  <p className="text-[11px] font-medium text-muted-foreground mt-0.5 line-clamp-1">{ring.stage}</p>
                  <p className="text-[11px] text-muted-foreground/75 mt-1.5 leading-relaxed line-clamp-2">
                    {ring.desc}
                  </p>
                </div>

                <div className="mt-3 pt-2.5 border-t border-border/40 space-y-1">
                  {ring.metrics.map((m, mIdx) => (
                    <div
                      key={mIdx}
                      className="text-[11px] text-foreground/90 font-medium flex items-center justify-between"
                    >
                      <span className="truncate">{m}</span>
                    </div>
                  ))}
                </div>
              </div>
            );
          })}
        </div>

        {/* Bottom subtle summary bar */}
        <div className="mt-4 pt-3 border-t border-border/50 flex flex-col sm:flex-row sm:items-center justify-between gap-2 text-xs text-muted-foreground">
          <div className="flex items-center gap-1.5">
            <Sparkles className="h-3.5 w-3.5 text-primary shrink-0" />
            <span className="line-clamp-1">{data.summary_text}</span>
          </div>
          <span className="shrink-0 font-medium text-foreground">
            {t('totalLearnings')}: {data.total_learnings_count}
          </span>
        </div>
      </CardContent>
    </Card>
  );
});

export default LearningLoopFiveRingHub;
