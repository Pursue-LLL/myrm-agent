'use client';

/**
 * [INPUT]
 * @/services/memory/commandCenter::MemoryBehavioralInsights, getBehavioralInsights, triggerBehavioralSync
 * @/components/features/icons/PremiumIcons::IconClock, IconUsers, IconActivity, IconRotateCcw, IconCheckCircle, IconChart
 *
 * [OUTPUT]
 * BehavioralMetricsPanel: Zero-model-cost deterministic behavioral routine visualization panel.
 *
 * [POS]
 * 记忆指挥中心行为洞察面板。展示纯确定性聚合的作息高峰分布（工作日/周末双轨切换）、
 * 响应时延分位数（P50/P90）、高频协作者 Top-K，无任何原生 emoji，支持深浅双色主题与国际化。
 */

import { memo, useCallback, useEffect, useState } from 'react';
import { useTranslations } from 'next-intl';
import { cn } from '@/lib/utils/classnameUtils';
import { toast } from '@/hooks/shared/useToast';
import {
  IconActivity,
  IconChart,
  IconCheckCircle,
  IconClock,
  IconRotateCcw,
  IconUsers,
} from '@/components/features/icons/PremiumIcons';
import {
  getBehavioralInsights,
  triggerBehavioralSync,
  type MemoryBehavioralInsights,
} from '@/services/memory/commandCenter';

interface BehavioralMetricsPanelProps {
  className?: string;
}

export const BehavioralMetricsPanel = memo(function BehavioralMetricsPanel({
  className,
  t: parentT,
}: BehavioralMetricsPanelProps & { t?: (key: string, values?: Record<string, string | number>) => string }) {
  const fallbackT = useTranslations('settings.memory.commandCenter.behavioral');
  const tb = parentT
    ? (key: string, values?: Record<string, string | number>) => parentT(`commandCenter.behavioral.${key}`, values)
    : (key: string, values?: Record<string, string | number>) => fallbackT(`commandCenter.behavioral.${key}` as Parameters<typeof fallbackT>[0], values);
  const [data, setData] = useState<MemoryBehavioralInsights | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [syncing, setSyncing] = useState<boolean>(false);
  const [activeTab, setActiveTab] = useState<'workday' | 'weekend' | 'combined'>('workday');

  const loadInsights = useCallback(async () => {
    try {
      setLoading(true);
      const res = await getBehavioralInsights(30);
      setData(res);
    } catch {
      toast.error(tb('loadError'));
    } finally {
      setLoading(false);
    }
  }, [tb]);

  useEffect(() => {
    void loadInsights();
  }, [loadInsights]);

  const handleSync = async () => {
    try {
      setSyncing(true);
      const res = await triggerBehavioralSync(30);
      if (res.count > 0) {
        toast.success(tb('syncSuccess', { count: res.count }));
        await loadInsights();
      } else {
        toast.info(tb('syncNoEligible'));
      }
    } catch {
      toast.error(tb('syncError'));
    } finally {
      setSyncing(false);
    }
  };

  const currentHistogram = (() => {
    if (!data) return [];
    if (activeTab === 'workday') return data.workday_hour_histogram;
    if (activeTab === 'weekend') return data.weekend_hour_histogram;
    return data.hour_histogram;
  })();

  const maxVal = Math.max(1, ...(currentHistogram || [1]));

  return (
    <div
      className={cn(
        'rounded-xl border border-zinc-200 dark:border-zinc-800 bg-white/70 dark:bg-zinc-900/70 backdrop-blur-md p-5 shadow-xs transition-all',
        className
      )}
    >
      {/* Header */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 pb-4 border-b border-zinc-100 dark:border-zinc-800/60">
        <div>
          <div className="flex items-center gap-2">
            <span className="p-1.5 rounded-lg bg-emerald-500/10 text-emerald-600 dark:text-emerald-400">
              <IconActivity className="w-4 h-4" />
            </span>
            <h3 className="text-sm font-semibold text-zinc-900 dark:text-zinc-100">
              {tb('title')}
            </h3>
            <span className="px-2 py-0.5 text-[11px] font-medium tracking-wide rounded-full bg-emerald-100/70 text-emerald-700 dark:bg-emerald-950/60 dark:text-emerald-300 border border-emerald-200/50 dark:border-emerald-800/40">
              {tb('zeroCostBadge')}
            </span>
          </div>
          <p className="text-xs text-zinc-500 dark:text-zinc-400 mt-1">
            {tb('subtitle')}
          </p>
          {data && (
            <div className="flex flex-wrap items-center gap-2 mt-2">
              <span className="inline-flex items-center gap-1 px-2 py-0.5 text-[10px] font-medium rounded-md bg-zinc-100 dark:bg-zinc-800 text-zinc-600 dark:text-zinc-300 border border-zinc-200/60 dark:border-zinc-700/60">
                <IconClock className="w-3 h-3 text-indigo-400" />
                <span>
                  {data.detected_timezone || (typeof Intl !== 'undefined' ? Intl.DateTimeFormat().resolvedOptions().timeZone : 'UTC')}
                  {data.offset_minutes !== undefined && data.offset_minutes !== null
                    ? ` (UTC${data.offset_minutes >= 0 ? '+' : ''}${(data.offset_minutes / 60).toFixed(1)}h)`
                    : ''}
                </span>
              </span>
              <span className="inline-flex items-center gap-1 px-2 py-0.5 text-[10px] font-medium rounded-md bg-zinc-100 dark:bg-zinc-800 text-zinc-600 dark:text-zinc-300 border border-zinc-200/60 dark:border-zinc-700/60">
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-500" />
                <span>{tb('localeAnchor', { locale: data.locale_anchor || 'Auto' })}</span>
              </span>
            </div>
          )}
        </div>

        <div className="flex items-center gap-2 self-end sm:self-auto">
          <button
            type="button"
            onClick={() => void loadInsights()}
            disabled={loading}
            aria-label={tb('refresh')}
            className="p-1.5 rounded-lg border border-zinc-200 dark:border-zinc-700 text-zinc-600 dark:text-zinc-300 hover:bg-zinc-100 dark:hover:bg-zinc-800 transition-colors disabled:opacity-50"
          >
            <IconRotateCcw className={cn('w-3.5 h-3.5', loading && 'animate-spin')} />
          </button>
          <button
            type="button"
            onClick={() => void handleSync()}
            disabled={syncing || loading}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-zinc-900 dark:bg-zinc-100 text-white dark:text-zinc-900 hover:bg-zinc-800 dark:hover:bg-zinc-200 shadow-xs transition-colors disabled:opacity-50"
          >
            <IconCheckCircle className={cn('w-3.5 h-3.5', syncing && 'animate-pulse')} />
            <span>{syncing ? tb('syncing') : tb('syncProfile')}</span>
          </button>
        </div>
      </div>

      {loading && !data ? (
        <div className="py-12 flex flex-col items-center justify-center text-xs text-zinc-400 dark:text-zinc-500 animate-pulse">
          <IconChart className="w-6 h-6 mb-2 opacity-40" />
          <span>{tb('analyzing')}</span>
        </div>
      ) : (
        <div className="space-y-6 pt-4">
          {/* Top Metrics Cards */}
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            {/* Peak Window */}
            <div className="p-3.5 rounded-lg border border-zinc-100 dark:border-zinc-800/80 bg-zinc-50/50 dark:bg-zinc-800/30">
              <div className="flex items-center gap-2 text-zinc-500 dark:text-zinc-400 text-xs mb-1">
                <IconClock className="w-3.5 h-3.5 text-indigo-500" />
                <span>{tb('peakActivity')}</span>
              </div>
              <div className="text-base font-semibold text-zinc-900 dark:text-zinc-100">
                {data?.workday_peak_window || data?.peak_active_window || tb('flexibleTime')}
              </div>
              <div className="text-[11px] text-zinc-400 dark:text-zinc-500 mt-0.5">
                {tb('sampleBase', { count: data?.self_message_count ?? 0 })}
              </div>
            </div>

            {/* Reply Latency */}
            <div className="p-3.5 rounded-lg border border-zinc-100 dark:border-zinc-800/80 bg-zinc-50/50 dark:bg-zinc-800/30">
              <div className="flex items-center gap-2 text-zinc-500 dark:text-zinc-400 text-xs mb-1">
                <IconActivity className="w-3.5 h-3.5 text-amber-500" />
                <span>{tb('replyLatency')}</span>
              </div>
              <div className="text-base font-semibold text-zinc-900 dark:text-zinc-100">
                {data?.reply_latency_p50_ms != null
                  ? `${(data.reply_latency_p50_ms / 1000).toFixed(1)}s`
                  : tb('notEnoughData')}
              </div>
              <div className="text-[11px] text-zinc-400 dark:text-zinc-500 mt-0.5">
                {data?.reply_latency_p90_ms != null
                  ? `P90: ${(data.reply_latency_p90_ms / 1000).toFixed(1)}s (${data.latency_sample_count} turns)`
                  : tb('minTurnsRequired')}
              </div>
            </div>

            {/* Top Partner */}
            <div className="p-3.5 rounded-lg border border-zinc-100 dark:border-zinc-800/80 bg-zinc-50/50 dark:bg-zinc-800/30">
              <div className="flex items-center gap-2 text-zinc-500 dark:text-zinc-400 text-xs mb-1">
                <IconUsers className="w-3.5 h-3.5 text-emerald-500" />
                <span>{tb('primaryCollaborator')}</span>
              </div>
              <div className="text-base font-semibold text-zinc-900 dark:text-zinc-100 truncate">
                {data?.top_collaborators && data.top_collaborators.length > 0
                  ? data.top_collaborators[0][0]
                  : tb('noneObserved')}
              </div>
              <div className="text-[11px] text-zinc-400 dark:text-zinc-500 mt-0.5">
                {data?.top_collaborators && data.top_collaborators.length > 0
                  ? tb('interactions', { count: data.top_collaborators[0][1] })
                  : tb('groupDiscussions')}
              </div>
            </div>
          </div>

          {/* Histogram Section */}
          <div>
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs font-medium text-zinc-700 dark:text-zinc-300">
                {tb('activeDistribution24h')}
              </span>
              <div className="flex items-center rounded-lg p-0.5 bg-zinc-100 dark:bg-zinc-800 text-[11px]">
                <button
                  type="button"
                  onClick={() => setActiveTab('workday')}
                  className={cn(
                    'px-2 py-0.5 rounded-md transition-all font-medium',
                    activeTab === 'workday'
                      ? 'bg-white dark:bg-zinc-700 text-zinc-900 dark:text-zinc-100 shadow-xs'
                      : 'text-zinc-500 hover:text-zinc-800 dark:hover:text-zinc-200'
                  )}
                >
                  {tb('workday')}
                </button>
                <button
                  type="button"
                  onClick={() => setActiveTab('weekend')}
                  className={cn(
                    'px-2 py-0.5 rounded-md transition-all font-medium',
                    activeTab === 'weekend'
                      ? 'bg-white dark:bg-zinc-700 text-zinc-900 dark:text-zinc-100 shadow-xs'
                      : 'text-zinc-500 hover:text-zinc-800 dark:hover:text-zinc-200'
                  )}
                >
                  {tb('weekend')}
                </button>
                <button
                  type="button"
                  onClick={() => setActiveTab('combined')}
                  className={cn(
                    'px-2 py-0.5 rounded-md transition-all font-medium',
                    activeTab === 'combined'
                      ? 'bg-white dark:bg-zinc-700 text-zinc-900 dark:text-zinc-100 shadow-xs'
                      : 'text-zinc-500 hover:text-zinc-800 dark:hover:text-zinc-200'
                  )}
                >
                  {tb('allDays')}
                </button>
              </div>
            </div>

            {/* 24-Bar Micro Histogram */}
            <div className="flex items-end gap-1 h-20 pt-2 px-1 border-b border-zinc-100 dark:border-zinc-800/80">
              {currentHistogram.map((count, hour) => {
                const heightPct = Math.max(6, Math.round((count / maxVal) * 100));
                const isHighlight =
                  count > 0 &&
                  (activeTab === 'workday'
                    ? data?.workday_peak_window
                    : activeTab === 'weekend'
                    ? data?.weekend_peak_window
                    : data?.peak_active_window);
                return (
                  <div
                    key={hour}
                    className="flex-1 flex flex-col items-center h-full justify-end group relative"
                  >
                    <div
                      style={{ height: `${heightPct}%` }}
                      className={cn(
                        'w-full rounded-t-xs transition-all duration-300',
                        count > 0
                          ? isHighlight
                            ? 'bg-indigo-500/80 hover:bg-indigo-600 dark:bg-indigo-400 dark:hover:bg-indigo-300'
                            : 'bg-zinc-400/60 dark:bg-zinc-600/60 hover:bg-zinc-500'
                          : 'bg-zinc-100 dark:bg-zinc-800/40'
                      )}
                    />
                    {/* Tooltip */}
                    <div className="absolute -top-7 opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none z-10 px-1.5 py-0.5 rounded bg-zinc-900 text-white text-[10px] whitespace-nowrap shadow-sm">
                      {hour}:00 - {count} msgs
                    </div>
                  </div>
                );
              })}
            </div>
            <div className="flex justify-between text-[10px] text-zinc-400 dark:text-zinc-500 mt-1 px-0.5">
              <span>00:00</span>
              <span>06:00</span>
              <span>12:00</span>
              <span>18:00</span>
              <span>23:00</span>
            </div>
          </div>

          {/* Collaborators List */}
          {data?.top_collaborators && data.top_collaborators.length > 0 && (
            <div className="pt-1">
              <span className="text-xs font-medium text-zinc-700 dark:text-zinc-300 mb-2 block">
                {tb('frequentCollaborators')}
              </span>
              <div className="flex flex-wrap gap-2">
                {data.top_collaborators.map(([name, count]) => (
                  <div
                    key={name}
                    className="flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs bg-zinc-100/70 dark:bg-zinc-800/50 text-zinc-700 dark:text-zinc-300 border border-zinc-200/50 dark:border-zinc-700/40"
                  >
                    <IconUsers className="w-3 h-3 text-zinc-400" />
                    <span className="font-medium">{name}</span>
                    <span className="text-[10px] text-zinc-400 dark:text-zinc-500 font-mono">
                      ×{count}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
});
