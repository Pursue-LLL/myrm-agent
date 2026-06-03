'use client';

import { useEffect, useState, useCallback } from 'react';
import { useTranslations } from 'next-intl';
import { Brain, Zap, CalendarDays, HeartPulse, Loader2, Sprout, RefreshCw } from 'lucide-react';
import { Button } from '@/components/primitives/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/primitives/card';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/primitives/tabs';
import { cn } from '@/lib/utils/classnameUtils';
import { getGrowthDashboard, type GrowthDashboardData } from '@/services/statistics';
import { showApiError } from '@/lib/api';

import ActivityHeatmap from './ActivityHeatmap';
import DailyJournal from './DailyJournal';
import HealthRadar from './HealthRadar';
import SkillEventList from './SkillEventList';

export default function GrowthDashboard() {
  const t = useTranslations('growthDashboard');
  const [data, setData] = useState<GrowthDashboardData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  const fetchData = useCallback(async () => {
    try {
      setLoading(true);
      setError(false);
      const result = await getGrowthDashboard();
      setData(result);
    } catch (e) {
      setError(true);
      showApiError(e);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (!data) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[60vh] gap-4">
        <Sprout className="h-16 w-16 text-muted-foreground/40" />
        <h2 className="text-xl font-semibold text-foreground">{t('empty.title')}</h2>
        <p className="text-muted-foreground text-sm">{t('empty.description')}</p>
        {error && (
          <Button variant="outline" size="sm" onClick={fetchData} className="mt-2">
            <RefreshCw className="h-4 w-4 mr-2" />
            {t('empty.retry')}
          </Button>
        )}
      </div>
    );
  }

  const { snapshot, activity_heatmap, weekly_summary, skill_events } = data;

  const kpiCards = [
    {
      icon: Brain,
      label: t('snapshot.totalMemories'),
      value: snapshot.total_memories,
      sub: snapshot.memory_week_delta > 0 ? t('snapshot.weekDelta', { count: snapshot.memory_week_delta }) : undefined,
      color: 'text-blue-500',
      bgColor: 'bg-blue-500/10',
    },
    {
      icon: Zap,
      label: t('snapshot.skills'),
      value: snapshot.total_skills,
      sub:
        snapshot.total_evolutions > 0
          ? `${snapshot.total_evolutions} ${t('snapshot.evolutions')}` +
            (snapshot.evolutions_apply_failed > 0
              ? ` · ${snapshot.evolutions_apply_failed} ${t('snapshot.applyFailed')}`
              : '')
          : undefined,
      color: snapshot.evolutions_apply_failed > 0 ? 'text-red-500' : 'text-amber-500',
      bgColor: snapshot.evolutions_apply_failed > 0 ? 'bg-red-500/10' : 'bg-amber-500/10',
    },
    {
      icon: CalendarDays,
      label: t('snapshot.activeDays'),
      value: snapshot.active_days,
      sub: snapshot.max_streak > 0 ? t('snapshot.streak', { count: snapshot.max_streak }) : undefined,
      color: 'text-green-500',
      bgColor: 'bg-green-500/10',
    },
    {
      icon: HeartPulse,
      label: t('snapshot.memoryHealth'),
      value: snapshot.memory_health_score,
      sub: undefined,
      color:
        snapshot.memory_health_score >= 70
          ? 'text-emerald-500'
          : snapshot.memory_health_score >= 40
            ? 'text-amber-500'
            : 'text-red-500',
      bgColor:
        snapshot.memory_health_score >= 70
          ? 'bg-emerald-500/10'
          : snapshot.memory_health_score >= 40
            ? 'bg-amber-500/10'
            : 'bg-red-500/10',
    },
  ];

  return (
    <div className="w-full max-w-6xl mx-auto px-4 py-6 md:px-6 md:py-8 space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-foreground">{t('title')}</h1>
        <p className="text-sm text-muted-foreground mt-1">{t('subtitle')}</p>
      </div>

      <Tabs defaultValue="overview" className="w-full">
        <TabsList>
          <TabsTrigger value="overview">{t('tabs.overview')}</TabsTrigger>
          <TabsTrigger value="daily">{t('tabs.daily')}</TabsTrigger>
        </TabsList>

        <TabsContent value="daily" className="mt-4">
          <DailyJournal />
        </TabsContent>

        <TabsContent value="overview" className="mt-4 space-y-6">
          {/* KPI Cards */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 md:gap-4">
            {kpiCards.map((card) => (
              <Card key={card.label} className="relative overflow-hidden">
                <CardContent className="p-4 md:p-5">
                  <div className="flex items-start justify-between">
                    <div className="space-y-1.5">
                      <p className="text-xs md:text-sm text-muted-foreground font-medium">{card.label}</p>
                      <p className="text-2xl md:text-3xl font-bold text-foreground">{card.value}</p>
                      {card.sub && <p className={cn('text-xs font-medium', card.color)}>{card.sub}</p>}
                    </div>
                    <div className={cn('p-2 rounded-lg', card.bgColor)}>
                      <card.icon className={cn('h-5 w-5', card.color)} />
                    </div>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>

          {/* Middle row: Heatmap + Health Radar */}
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
            <Card className="lg:col-span-2">
              <CardHeader className="pb-2 px-4 pt-4 md:px-6 md:pt-5">
                <CardTitle className="text-base font-semibold">{t('activityHeatmap.title')}</CardTitle>
              </CardHeader>
              <CardContent className="px-4 pb-4 md:px-6 md:pb-5">
                <ActivityHeatmap data={activity_heatmap} />
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="pb-2 px-4 pt-4 md:px-6 md:pt-5">
                <CardTitle className="text-base font-semibold">{t('healthRadar.title')}</CardTitle>
              </CardHeader>
              <CardContent className="px-4 pb-4 md:px-6 md:pb-5">
                <HealthRadar dimensions={snapshot.memory_health_dimensions} score={snapshot.memory_health_score} />
              </CardContent>
            </Card>
          </div>

          {/* Bottom row: Weekly Summary + Skill Events */}
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
            {/* Weekly Summary */}
            <Card>
              <CardHeader className="pb-2 px-4 pt-4 md:px-6 md:pt-5">
                <CardTitle className="text-base font-semibold">{t('weeklySummary.title')}</CardTitle>
              </CardHeader>
              <CardContent className="px-4 pb-4 md:px-6 md:pb-5">
                <div className="space-y-4">
                  <WeeklyMetric
                    label={t('weeklySummary.conversations')}
                    value={weekly_summary.conversations}
                    previousValue={weekly_summary.previous_conversations}
                  />
                  <WeeklyMetric
                    label={t('weeklySummary.messages')}
                    value={weekly_summary.messages_sent}
                    previousValue={weekly_summary.previous_messages_sent}
                  />
                  <WeeklyMetric
                    label={t('weeklySummary.cronExecutions')}
                    value={weekly_summary.cron_executions}
                    previousValue={weekly_summary.previous_cron_executions}
                  />
                  <WeeklyMetric
                    label={t('weeklySummary.toolCalls')}
                    value={weekly_summary.tool_calls}
                    previousValue={weekly_summary.previous_tool_calls}
                  />
                </div>
              </CardContent>
            </Card>

            {/* Skill Evolution Log */}
            <Card className="lg:col-span-2">
              <CardHeader className="pb-2 px-4 pt-4 md:px-6 md:pt-5">
                <CardTitle className="text-base font-semibold">{t('skillEvents.title')}</CardTitle>
              </CardHeader>
              <CardContent className="px-4 pb-4 md:px-6 md:pb-5">
                <SkillEventList events={skill_events} />
              </CardContent>
            </Card>
          </div>
        </TabsContent>
      </Tabs>
    </div>
  );
}

function WeeklyMetric({ label, value, previousValue }: { label: string; value: number; previousValue?: number }) {
  const delta = previousValue !== undefined ? value - previousValue : undefined;
  const hasChange = delta !== undefined && delta !== 0;
  const isPositive = delta !== undefined && delta > 0;

  const percentText =
    hasChange && previousValue ? `${isPositive ? '+' : ''}${Math.round((delta / previousValue) * 100)}%` : undefined;

  return (
    <div className="flex items-center justify-between">
      <span className="text-sm text-muted-foreground">{label}</span>
      <div className="flex items-center gap-2">
        <span className="text-lg font-semibold text-foreground">{value.toLocaleString()}</span>
        {hasChange && (
          <span className={cn('text-xs font-medium', isPositive ? 'text-emerald-500' : 'text-red-500')}>
            {isPositive ? '↑' : '↓'}
            {Math.abs(delta).toLocaleString()}
            {percentText && <span className="ml-0.5 opacity-70">({percentText})</span>}
          </span>
        )}
        {delta === 0 && previousValue !== undefined && <span className="text-xs text-muted-foreground">=</span>}
      </div>
    </div>
  );
}
