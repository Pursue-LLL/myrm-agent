'use client';

import { memo, useCallback, useEffect, useState } from 'react';
import { useLocale, useTranslations } from 'next-intl';
import { motion } from 'framer-motion';
import {
  IconDatabase,
  IconBrain,
  IconChat,
  IconRefresh,
  IconAlertCircle,
  IconChart,
  IconArrowRight,
  IconChevronDown,
  IconChevronUp,
} from '@/components/ui/icons/PremiumIcons';
import SettingsSection from './SettingsSection';
import BudgetPolicySection from './BudgetPolicySection';
import MemoryGuardianCard from './MemoryGuardianCard';
import RoutingAnalyticsPanel, { formatTokenCount, formatCost } from './RoutingAnalyticsPanel';
import SessionAnalyticsDialog from './SessionAnalyticsDialog';
import { localizeReactNode } from '@/lib/utils/localeText';
import {
  getDailyUsage,
  getSessionUsage,
  getUsageStatistics,
  getGlobalActivityPatterns,
  getTopSessions,
  getModelSessions,
  type DailyUsage,
  type SessionUsage,
  type UsageStats,
  type GlobalActivityPatterns,
  type TopSession,
  type ModelSessionItem,
} from '@/services/statistics';
import { IconClock, IconTarget } from '@/components/ui/icons/PremiumIcons';
import { cn } from '@/lib/utils/classnameUtils';

// --- Stat Card ---

interface StatCardProps {
  icon: React.ElementType;
  label: string;
  value: string;
  subValue?: string;
  colorClass: string;
}

const StatCard = memo<StatCardProps>(({ icon: Icon, label, value, subValue, colorClass }) => (
  <div className="flex flex-col gap-2 p-4 rounded-xl bg-background/60 border border-border/40">
    <div className="flex items-center gap-2">
      <div className={cn('w-8 h-8 rounded-lg flex items-center justify-center', colorClass)}>
        <Icon className="w-4 h-4 text-inherit" />
      </div>
      <span className="text-xs text-muted-foreground font-medium">{label}</span>
    </div>
    <div className="flex items-baseline gap-1.5">
      <span className="text-xl font-bold tabular-nums text-foreground">{value}</span>
      {subValue && <span className="text-xs text-muted-foreground">{subValue}</span>}
    </div>
  </div>
));
StatCard.displayName = 'StatCard';

// --- Cache Break Timeline ---

const CacheBreakTimeline = memo<{ data: DailyUsage[]; t: ReturnType<typeof useTranslations> }>(({ data, t }) => {
  const hasBreaks = data.some((d) => Object.keys(d.cacheBreakCounts || {}).length > 0);
  if (!hasBreaks) return null;

  // Aggregate all unique break reasons
  const allReasons = new Set<string>();
  data.forEach((d) => {
    Object.keys(d.cacheBreakCounts || {}).forEach((r) => allReasons.add(r));
  });

  const reasons = Array.from(allReasons);
  const maxCount = Math.max(...data.flatMap((d) => Object.values(d.cacheBreakCounts || {})));

  return (
    <div className="mt-6 pt-4 border-t border-border/40">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2 text-xs font-medium text-foreground">
          <IconAlertCircle className="w-3.5 h-3.5 text-amber-500" />
          {t('cacheBreakDiagnostics') || 'Cache Diagnostic Timeline'}
        </div>
        <div className="text-[10px] text-muted-foreground flex gap-3">
          <div className="flex items-center gap-1">
            <span className="w-2 h-2 rounded-sm bg-amber-500/20" /> Low
          </div>
          <div className="flex items-center gap-1">
            <span className="w-2 h-2 rounded-sm bg-amber-500/60" /> Med
          </div>
          <div className="flex items-center gap-1">
            <span className="w-2 h-2 rounded-sm bg-amber-500" /> High
          </div>
        </div>
      </div>
      <div className="space-y-1.5">
        {reasons.map((reason) => (
          <div key={reason} className="flex gap-2 items-center">
            <div
              className="w-28 shrink-0 text-[9px] text-muted-foreground truncate"
              title={t(`reasons.${reason}`) || reason}
            >
              {t(`reasons.${reason}`) || reason}
            </div>
            <div className="flex-1 flex gap-1 h-3.5 px-1">
              {data.map((d) => {
                const count = d.cacheBreakCounts?.[reason] || 0;
                let opacityClass = 'bg-amber-500/5';
                if (count > 0) {
                  const intensity = count / maxCount;
                  if (intensity > 0.6) opacityClass = 'bg-amber-500';
                  else if (intensity > 0.2) opacityClass = 'bg-amber-500/60';
                  else opacityClass = 'bg-amber-500/30';
                }
                return (
                  <div key={d.date} className={cn('flex-1 rounded-sm transition-colors relative group', opacityClass)}>
                    {count > 0 && (
                      <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-1.5 hidden group-hover:block z-20 pointer-events-none">
                        <div className="bg-popover/95 backdrop-blur-sm border border-border/50 rounded shadow-lg px-2 py-1 text-[10px] whitespace-nowrap text-foreground">
                          {d.date}: <span className="font-bold text-amber-500">{count}</span> breaks
                        </div>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
});
CacheBreakTimeline.displayName = 'CacheBreakTimeline';

// --- Daily Bar Chart ---

const GRID_LINES = [0.25, 0.5, 0.75] as const;

function getLabelIndices(len: number): Set<number> {
  if (len <= 7) return new Set(Array.from({ length: len }, (_, i) => i));
  const step = Math.ceil(len / 5);
  const indices = new Set<number>();
  for (let i = 0; i < len; i += step) indices.add(i);
  indices.add(len - 1);
  return indices;
}

const DailyChart = memo<{ data: DailyUsage[]; t: ReturnType<typeof useTranslations> }>(({ data, t }) => {
  if (data.length === 0) {
    return <div className="flex items-center justify-center h-40 text-sm text-muted-foreground">{t('noData')}</div>;
  }

  const maxTokens = Math.max(...data.map((d) => d.totalTokens), 1);
  const labelIndices = getLabelIndices(data.length);

  const points = data
    .map((d, idx) => {
      const cacheRate = d.inputTokens > 0 ? d.cachedTokens / d.inputTokens : 0;
      const x = (idx + 0.5) * (100 / data.length);
      const y = 100 - cacheRate * 100;
      return `${x},${y}`;
    })
    .join(' ');

  return (
    <div className="space-y-2">
      <div className="flex items-center gap-2 text-sm font-medium text-foreground">
        <IconChart className="w-4 h-4 text-primary" />
        {t('dailyTrend')}
      </div>

      <div className="flex gap-2">
        {/* Y-axis */}
        <div className="flex flex-col justify-between shrink-0 w-10 text-[9px] tabular-nums text-muted-foreground/50 text-right h-40">
          <span>{formatTokenCount(maxTokens)}</span>
          <span>{formatTokenCount(maxTokens * 0.5)}</span>
          <span>0</span>
        </div>

        {/* Chart + X-axis */}
        <div className="flex-1 min-w-0">
          <div className="relative h-40 rounded-lg overflow-hidden">
            {/* Background gradient */}
            <div className="absolute inset-0 bg-gradient-to-t from-muted/30 to-transparent pointer-events-none" />

            {/* Grid lines */}
            {GRID_LINES.map((ratio) => (
              <div
                key={ratio}
                className="absolute left-0 right-0 border-t border-dashed border-border/25"
                style={{ bottom: `${ratio * 100}%` }}
              />
            ))}
            <div className="absolute bottom-0 left-0 right-0 h-px bg-border/40" />

            {/* Bars */}
            <div className="flex items-end gap-2 h-full justify-center px-1">
              {data.map((d, i) => {
                const barH = Math.max((d.totalTokens / maxTokens) * 100, 2);
                const cacheRate = d.inputTokens > 0 ? ((d.cachedTokens / d.inputTokens) * 100).toFixed(1) : null;
                return (
                  <div key={d.date} className="group relative flex-1 min-w-0 max-w-12 h-full flex flex-col justify-end">
                    <motion.div
                      className="relative w-full rounded-t-lg overflow-hidden cursor-default"
                      style={{ height: `${barH}%`, transformOrigin: 'bottom' }}
                      initial={{ scaleY: 0 }}
                      animate={{ scaleY: 1 }}
                      transition={{ delay: i * 0.04, duration: 0.45, ease: [0.22, 1, 0.36, 1] }}
                      whileHover={{ scale: 1.04 }}
                    >
                      <div className="absolute inset-0 bg-gradient-to-t from-primary/40 to-primary/90" />
                      <div className="absolute inset-0 opacity-0 group-hover:opacity-100 bg-primary/20 transition-opacity duration-200" />
                    </motion.div>

                    {/* Tooltip */}
                    <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2.5 hidden group-hover:block z-30 pointer-events-none">
                      <div className="bg-popover/95 backdrop-blur-sm border border-border/50 rounded-xl shadow-xl ring-1 ring-black/[0.03] px-3.5 py-2.5 text-xs whitespace-nowrap">
                        <div className="font-semibold text-foreground">{d.date}</div>
                        <div className="text-muted-foreground mt-1 flex items-center gap-1">
                          <span className="inline-block w-1.5 h-1.5 rounded-sm bg-primary" />
                          {formatTokenCount(d.totalTokens)} tokens
                        </div>
                        {cacheRate !== null && (
                          <div className="text-emerald-600 dark:text-emerald-400 mt-0.5 flex items-center gap-1">
                            <span className="inline-block w-1.5 h-1.5 rounded-full bg-emerald-500" />
                            {t('cacheHitRate')}: {cacheRate}%
                            {d.cacheSavingsUsd ? ` (-${formatCost(d.cacheSavingsUsd)})` : ''}
                          </div>
                        )}
                        {d.costUsd > 0 && <div className="text-muted-foreground mt-0.5">{formatCost(d.costUsd)}</div>}
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>

            {/* SVG Trend Line Overlay */}
            <div className="absolute inset-0 pointer-events-none px-1 py-[2px]">
              <svg viewBox="0 0 100 100" preserveAspectRatio="none" className="w-full h-full overflow-visible">
                <motion.polyline
                  initial={{ pathLength: 0, opacity: 0 }}
                  animate={{ pathLength: 1, opacity: 1 }}
                  transition={{ duration: 1, delay: 0.5 }}
                  points={points}
                  fill="none"
                  stroke="rgb(16 185 129)"
                  strokeWidth="1.5"
                  vectorEffect="non-scaling-stroke"
                  className="drop-"
                />
                {data.map((d, idx) => {
                  const cacheRate = d.inputTokens > 0 ? d.cachedTokens / d.inputTokens : 0;
                  const x = (idx + 0.5) * (100 / data.length);
                  const y = 100 - cacheRate * 100;
                  return (
                    <circle
                      key={idx}
                      cx={`${x}%`}
                      cy={`${y}%`}
                      r="2.5"
                      fill="rgb(16 185 129)"
                      className="stroke-background stroke-[1px]"
                    />
                  );
                })}
              </svg>
            </div>
          </div>

          {/* X-axis labels */}
          <div className="flex gap-2 mt-2 justify-center px-1">
            {data.map((d, i) => (
              <div key={d.date} className="flex-1 min-w-0 max-w-12 text-center">
                {labelIndices.has(i) && (
                  <span className="text-[10px] text-muted-foreground/60 truncate block">{d.date.slice(5)}</span>
                )}
              </div>
            ))}
          </div>
        </div>

        {/* Right Y-axis (Cache Hit Rate) */}
        <div className="flex flex-col justify-between shrink-0 w-8 text-[9px] tabular-nums text-emerald-600/70 dark:text-emerald-400/70 text-left h-40">
          <span>100%</span>
          <span>50%</span>
          <span>0%</span>
        </div>
      </div>

      {/* Legend */}
      <div className="flex justify-center gap-6 mt-2 pt-2 border-t border-border/20 text-[10px] text-muted-foreground">
        <div className="flex items-center gap-1.5">
          <span className="w-2 h-2 rounded-sm bg-primary/80" />
          {t('totalTokens')}
        </div>
        <div className="flex items-center gap-1.5">
          <span className="w-2 h-2 rounded-full bg-emerald-500" />
          {t('cacheHitRate')}
        </div>
      </div>

      {/* Cache Break Timeline */}
      <CacheBreakTimeline data={data} t={t} />
    </div>
  );
});
DailyChart.displayName = 'DailyChart';

// --- Session Table ---

const SessionTable = memo<{
  sessions: SessionUsage[];
  t: ReturnType<typeof useTranslations>;
  onSelectSession: (id: string) => void;
}>(({ sessions, t, onSelectSession }) => {
  if (sessions.length === 0) {
    return <div className="flex items-center justify-center h-20 text-sm text-muted-foreground">{t('noData')}</div>;
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2 text-sm font-medium text-foreground">
        <IconChat className="w-4 h-4 text-primary" />
        {t('topSessions')}
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="border-b border-border/50">
              <th className="text-left py-2 pr-3 text-muted-foreground font-medium">{t('session')}</th>
              <th className="text-right py-2 px-2 text-muted-foreground font-medium">{t('messages')}</th>
              <th className="text-right py-2 px-2 text-muted-foreground font-medium">{t('tokens')}</th>
              <th className="text-right py-2 pl-2 text-muted-foreground font-medium">{t('cost')}</th>
            </tr>
          </thead>
          <tbody>
            {sessions.slice(0, 10).map((s) => (
              <tr
                key={s.chatId}
                className="border-b border-border/30 last:border-0 cursor-pointer hover:bg-muted/50 transition-colors"
                onClick={() => onSelectSession(s.chatId)}
              >
                <td className="py-2 pr-3 max-w-[200px] truncate text-foreground" title={s.title}>
                  {s.title}
                </td>
                <td className="py-2 px-2 text-right tabular-nums text-muted-foreground">{s.messageCount}</td>
                <td className="py-2 px-2 text-right tabular-nums font-medium text-foreground">
                  {formatTokenCount(s.totalTokens)}
                </td>
                <td className="py-2 pl-2 text-right tabular-nums text-muted-foreground">
                  {s.costUsd > 0 ? formatCost(s.costUsd) : '—'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
});
SessionTable.displayName = 'SessionTable';

// --- Week Distribution Bar Chart ---

const WeekDistributionChart = memo<{ data: Record<number, number> }>(({ data }) => {
  const weekDays = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
  const values = weekDays.map((_, idx) => data[idx.toString()] || data[idx] || 0);
  const maxValue = Math.max(...values, 1);

  return (
    <div className="flex gap-2">
      <div className="flex flex-col justify-between shrink-0 w-10 text-[9px] tabular-nums text-muted-foreground/50 text-right h-40">
        <span>{maxValue}</span>
        <span>{Math.floor(maxValue / 2)}</span>
        <span>0</span>
      </div>

      <div className="flex-1 min-w-0">
        <div className="relative h-40 rounded-lg overflow-hidden">
          <div className="absolute inset-0 bg-gradient-to-b from-background/40 to-background/80" />
          <div className="relative h-full flex items-end gap-2 px-2">
            {values.map((val, idx) => {
              const heightPercent = (val / maxValue) * 100;
              return (
                <div key={idx} className="flex-1 flex flex-col items-center gap-1">
                  <motion.div
                    initial={{ height: 0 }}
                    animate={{ height: `${heightPercent}%` }}
                    transition={{ duration: 0.5, delay: idx * 0.05 }}
                    className="w-full rounded-t bg-primary/85 hover:bg-primary transition-colors"
                    title={`${weekDays[idx]}: ${val} tool calls`}
                  />
                </div>
              );
            })}
          </div>
        </div>
        <div className="flex gap-2 px-2 mt-2">
          {weekDays.map((day, idx) => (
            <div key={idx} className="flex-1 text-center text-[10px] text-muted-foreground font-medium">
              {day}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
});
WeekDistributionChart.displayName = 'WeekDistributionChart';

// --- Daily Trend Bar Chart ---

const ActivityDailyChart = memo<{ data: Array<{ date: string; tool_calls: number }> }>(({ data }) => {
  if (!data || data.length === 0) return null;

  const maxValue = Math.max(...data.map((d) => d.tool_calls), 1);
  const labels = data.map((d) => {
    const date = new Date(d.date);
    return `${date.getMonth() + 1}/${date.getDate()}`;
  });

  return (
    <div className="flex gap-2">
      <div className="flex flex-col justify-between shrink-0 w-10 text-[9px] tabular-nums text-muted-foreground/50 text-right h-40">
        <span>{maxValue}</span>
        <span>{Math.floor(maxValue / 2)}</span>
        <span>0</span>
      </div>

      <div className="flex-1 min-w-0">
        <div className="relative h-40 rounded-lg overflow-hidden">
          <div className="absolute inset-0 bg-gradient-to-b from-background/40 to-background/80" />
          <div className="relative h-full flex items-end gap-1 px-2">
            {data.map((item, idx) => {
              const heightPercent = (item.tool_calls / maxValue) * 100;
              return (
                <div key={idx} className="flex-1 flex flex-col items-center gap-1">
                  <motion.div
                    initial={{ height: 0 }}
                    animate={{ height: `${heightPercent}%` }}
                    transition={{ duration: 0.5, delay: idx * 0.03 }}
                    className="w-full rounded-t bg-primary/85 hover:bg-primary transition-colors"
                    title={`${item.date}: ${item.tool_calls} tool calls`}
                  />
                </div>
              );
            })}
          </div>
        </div>
        <div className="flex gap-1 px-2 mt-2">
          {labels.map((label, idx) => (
            <div key={idx} className="flex-1 text-center text-[9px] text-muted-foreground font-medium">
              {label}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
});
ActivityDailyChart.displayName = 'ActivityDailyChart';

// --- Hour Distribution Line Chart ---

const HourDistributionChart = memo<{ data: Record<number, number> }>(({ data }) => {
  const hours = Array.from({ length: 24 }, (_, i) => i);
  const values = hours.map((h) => data[h] || 0);
  const maxValue = Math.max(...values, 1);

  const points = values
    .map((val, idx) => {
      const x = (idx / 23) * 100;
      const y = 100 - (val / maxValue) * 100;
      return `${x},${y}`;
    })
    .join(' ');

  const pathD = `M 0,100 L ${points} L 100,100 Z`;

  return (
    <div className="flex gap-2">
      <div className="flex flex-col justify-between shrink-0 w-10 text-[9px] tabular-nums text-muted-foreground/50 text-right h-40">
        <span>{maxValue}</span>
        <span>{Math.floor(maxValue / 2)}</span>
        <span>0</span>
      </div>

      <div className="flex-1 min-w-0">
        <div className="relative h-40 rounded-lg overflow-hidden">
          <div className="absolute inset-0 bg-gradient-to-b from-background/40 to-background/80" />
          <svg viewBox="0 0 100 100" preserveAspectRatio="none" className="w-full h-full">
            <motion.path
              initial={{ pathLength: 0 }}
              animate={{ pathLength: 1 }}
              transition={{ duration: 1 }}
              d={pathD}
              fill="url(#gradient)"
              stroke="rgb(var(--primary))"
              strokeWidth="0.5"
              vectorEffect="non-scaling-stroke"
            />
            <defs>
              <linearGradient id="gradient" x1="0%" y1="0%" x2="0%" y2="100%">
                <stop offset="0%" stopColor="rgb(var(--primary))" stopOpacity="0.3" />
                <stop offset="100%" stopColor="rgb(var(--primary))" stopOpacity="0.05" />
              </linearGradient>
            </defs>
          </svg>
        </div>
        <div className="flex justify-between px-2 mt-2 text-[10px] text-muted-foreground font-medium">
          <span>00:00</span>
          <span>06:00</span>
          <span>12:00</span>
          <span>18:00</span>
          <span>23:00</span>
        </div>
      </div>
    </div>
  );
});
HourDistributionChart.displayName = 'HourDistributionChart';

// --- Model Breakdown Item (Collapsible) ---

interface ModelBreakdownItemProps {
  model: string;
  data: any;
  totalTokens: number;
  t: ReturnType<typeof useTranslations>;
  timeRange: number;
  onSelectSession: (id: string) => void;
}

const ModelBreakdownItem = memo<ModelBreakdownItemProps>(
  ({ model, data, totalTokens, t, timeRange, onSelectSession }) => {
    const [expanded, setExpanded] = useState(false);
    const [sessions, setSessions] = useState<ModelSessionItem[]>([]);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);

    const pct = totalTokens > 0 ? Math.round((data.totalTokens / totalTokens) * 100) : 0;
    const cacheRate = data.inputTokens > 0 ? Math.round((data.cachedTokens / data.inputTokens) * 100) : 0;

    useEffect(() => {
      if (!expanded) return;
      const fetchSessions = async () => {
        setLoading(true);
        setError(null);
        try {
          const list = await getModelSessions(model, timeRange);
          setSessions(list);
        } catch (err) {
          console.error('Failed to load sessions:', err);
          setError(t('retry'));
        } finally {
          setLoading(false);
        }
      };
      fetchSessions();
    }, [expanded, model, timeRange, t]);

    return (
      <div className="p-3 rounded-lg bg-background/40 border border-border/30 space-y-2 transition-all">
        <div
          className="flex items-center justify-between gap-2 cursor-pointer select-none group"
          onClick={() => setExpanded(!expanded)}
          role="button"
          tabIndex={0}
          title={expanded ? t('hideSessions') : t('showSessions')}
        >
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-1.5">
              <div className="text-xs font-semibold text-foreground truncate group-hover:text-primary transition-colors">
                {model.split('/').pop()}
              </div>
              {expanded ? (
                <IconChevronUp className="w-3.5 h-3.5 text-muted-foreground/60" />
              ) : (
                <IconChevronDown className="w-3.5 h-3.5 text-muted-foreground/60 opacity-0 group-hover:opacity-100 transition-opacity" />
              )}
            </div>
            <div className="text-[10px] text-muted-foreground mt-0.5">
              {data.calls} {t('calls')} · {formatTokenCount(data.totalTokens)} tokens
            </div>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            <div className="w-16 h-1.5 rounded-full bg-border/50 overflow-hidden">
              <div className="h-full rounded-full bg-primary transition-all" style={{ width: `${pct}%` }} />
            </div>
            <span className="text-[10px] tabular-nums text-muted-foreground w-8 text-right">{pct}%</span>
          </div>
        </div>

        <div className="grid grid-cols-2 sm:grid-cols-4 gap-x-4 gap-y-1 text-[10px] pt-1.5 border-t border-border/20">
          <div className="flex justify-between">
            <span className="text-muted-foreground">{t('inputTokens')}</span>
            <span className="tabular-nums text-foreground">{formatTokenCount(data.inputTokens)}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-muted-foreground">{t('outputTokens')}</span>
            <span className="tabular-nums text-foreground">{formatTokenCount(data.outputTokens)}</span>
          </div>
          {data.cachedTokens > 0 && (
            <div className="flex justify-between">
              <span className="text-muted-foreground">{t('cachedTokens')}</span>
              <span className="tabular-nums text-emerald-600 dark:text-emerald-400">
                {formatTokenCount(data.cachedTokens)} ({cacheRate}%)
              </span>
            </div>
          )}
          {data.costUsd > 0 && (
            <div className="flex justify-between">
              <span className="text-muted-foreground">{t('cost')}</span>
              <span className="tabular-nums text-foreground">{formatCost(data.costUsd)}</span>
            </div>
          )}
        </div>

        {expanded && (
          <div className="mt-3 pt-3 border-t border-border/20 space-y-2">
            <div className="text-[10px] uppercase font-bold tracking-widest text-muted-foreground/80 flex items-center gap-1">
              <IconChat className="w-3 h-3 text-muted-foreground" />
              {t('sessionDrilldown')}
            </div>

            {loading ? (
              <div className="flex items-center justify-center py-4">
                <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-primary" />
              </div>
            ) : error ? (
              <div className="flex items-center justify-between py-2 text-[10px] text-destructive">
                <span>{error}</span>
                <button onClick={() => setExpanded(false)} className="text-xs text-primary hover:underline">
                  {t('retry')}
                </button>
              </div>
            ) : sessions.length === 0 ? (
              <div className="text-[10px] text-muted-foreground/60 py-2 italic text-center">{t('noModelSessions')}</div>
            ) : (
              <div className="overflow-x-auto rounded-lg border border-border/25 bg-muted/15">
                <table className="w-full text-[10px] text-left">
                  <thead>
                    <tr className="border-b border-border/20 bg-muted/20 text-muted-foreground font-medium">
                      <th className="py-1.5 px-2 text-left">{t('session')}</th>
                      <th className="py-1.5 px-1.5 text-center">{t('messages')}</th>
                      <th className="py-1.5 px-1.5 text-right">{t('tokens')}</th>
                      <th className="py-1.5 px-2 text-right">{t('cost')}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {sessions.map((item) => (
                      <tr
                        key={item.chatId}
                        className="border-b border-border/10 last:border-0 hover:bg-muted/30 cursor-pointer transition-colors"
                        onClick={() => onSelectSession(item.chatId)}
                      >
                        <td className="py-2 px-2 max-w-[120px] sm:max-w-[180px] truncate">
                          <div className="font-medium text-foreground truncate">{item.title}</div>
                          <div className="text-[8px] text-muted-foreground/60 mt-0.5 flex items-center gap-1">
                            <span className="capitalize">{item.actionMode}</span>
                            <span>·</span>
                            <span>{item.lastUsedAt ? new Date(item.lastUsedAt).toLocaleDateString() : ''}</span>
                          </div>
                        </td>
                        <td className="py-2 px-1.5 text-center tabular-nums text-muted-foreground">{item.calls}</td>
                        <td className="py-2 px-1.5 text-right tabular-nums text-muted-foreground">
                          <div>{formatTokenCount(item.totalTokens)}</div>
                          <div className="text-[8px] text-muted-foreground/40 mt-0.5">
                            I {formatTokenCount(item.inputTokens)} / O {formatTokenCount(item.outputTokens)}
                          </div>
                        </td>
                        <td className="py-2 px-2 text-right tabular-nums text-foreground font-medium">
                          {formatCost(item.costUsd)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}
      </div>
    );
  },
);
ModelBreakdownItem.displayName = 'ModelBreakdownItem';

// --- Model Breakdown ---

interface ModelBreakdownProps {
  stats: UsageStats;
  t: ReturnType<typeof useTranslations>;
  timeRange: number;
  onSelectSession: (id: string) => void;
}

const ModelBreakdown = memo<ModelBreakdownProps>(({ stats, t, timeRange, onSelectSession }) => {
  const models = Object.entries(stats.modelBreakdown);
  if (models.length === 0) return null;

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2 text-sm font-medium text-foreground">
        <IconChart className="w-4 h-4 text-primary" />
        {t('modelBreakdown')}
      </div>
      <div className="grid gap-2">
        {models.map(([model, data]) => (
          <ModelBreakdownItem
            key={model}
            model={model}
            data={data}
            totalTokens={stats.totalTokens}
            t={t}
            timeRange={timeRange}
            onSelectSession={onSelectSession}
          />
        ))}
      </div>
    </div>
  );
});
ModelBreakdown.displayName = 'ModelBreakdown';

// --- Privacy Route Panel ---

const PrivacyRoutePanel = memo<{
  breakdown: Record<string, number>;
  t: ReturnType<typeof useTranslations>;
}>(({ breakdown, t }) => {
  const total = Object.values(breakdown).reduce((a, b) => a + b, 0);
  if (total === 0) return null;

  const localCount = breakdown['local'] ?? 0;
  const cloudCount = breakdown['cloud'] ?? 0;
  const localPct = Math.round((localCount / total) * 100);
  const cloudPct = 100 - localPct;

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2 text-xs text-muted-foreground">
        <span>{t('privacyRoutingDesc')}</span>
      </div>
      <div className="h-3 rounded-full overflow-hidden flex bg-muted">
        {localPct > 0 && (
          <div className="bg-green-500 dark:bg-green-400 transition-all" style={{ width: `${localPct}%` }} />
        )}
        {cloudPct > 0 && (
          <div className="bg-blue-500 dark:bg-blue-400 transition-all" style={{ width: `${cloudPct}%` }} />
        )}
      </div>
      <div className="grid grid-cols-2 gap-3">
        <div className="p-3 rounded-lg border border-border bg-background">
          <div className="flex items-center gap-2 mb-1">
            <div className="w-2.5 h-2.5 rounded-full bg-green-500 dark:bg-green-400" />
            <span className="text-xs font-medium text-foreground">{t('privacyRouteLocal')}</span>
          </div>
          <div className="text-lg font-bold text-foreground">{localCount}</div>
          <div className="text-[10px] text-muted-foreground">{localPct}%</div>
        </div>
        <div className="p-3 rounded-lg border border-border bg-background">
          <div className="flex items-center gap-2 mb-1">
            <div className="w-2.5 h-2.5 rounded-full bg-blue-500 dark:bg-blue-400" />
            <span className="text-xs font-medium text-foreground">{t('privacyRouteCloud')}</span>
          </div>
          <div className="text-lg font-bold text-foreground">{cloudCount}</div>
          <div className="text-[10px] text-muted-foreground">{cloudPct}%</div>
        </div>
      </div>
    </div>
  );
});
PrivacyRoutePanel.displayName = 'PrivacyRoutePanel';

// --- Main Section ---

function UsageStatisticsSection() {
  const t = useTranslations('settings.usageStatistics');
  const locale = useLocale();
  const [stats, setStats] = useState<UsageStats | null>(null);
  const [daily, setDaily] = useState<DailyUsage[]>([]);
  const [sessions, setSessions] = useState<SessionUsage[]>([]);
  const [activity, setActivity] = useState<GlobalActivityPatterns | null>(null);
  const [topSessions, setTopSessions] = useState<TopSession[]>([]);
  const [topSessionMetric, setTopSessionMetric] = useState<'duration' | 'messages' | 'tokens' | 'tool_calls'>(
    'duration',
  );
  const [timeRange, setTimeRange] = useState<7 | 30 | 365>(30);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedSessionId, setSelectedSessionId] = useState<string | null>(null);

  const fetchData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [statsData, dailyData, sessionData, activityData, topSessionsData] = await Promise.all([
        getUsageStatistics(),
        getDailyUsage(30),
        getSessionUsage(10),
        getGlobalActivityPatterns(timeRange),
        getTopSessions(topSessionMetric, 10, timeRange),
      ]);
      setStats(statsData);
      setDaily(dailyData.daily);
      setSessions(sessionData.sessions);
      setActivity(activityData);
      setTopSessions(topSessionsData);
    } catch (e) {
      console.error('[UsageStatistics] Failed to load data:', e);
      setError(e instanceof Error ? e.message : 'Failed to load statistics');
    } finally {
      setLoading(false);
    }
  }, [timeRange, topSessionMetric]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  if (loading) {
    return (
      <div className="space-y-6">
        <SettingsSection title={t('title')} description={t('description')}>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            {Array.from({ length: 4 }).map((_, i) => (
              <div key={i} className="h-24 rounded-xl bg-background/60 animate-pulse" />
            ))}
          </div>
          <div className="h-40 rounded-xl bg-background/60 animate-pulse" />
        </SettingsSection>
      </div>
    );
  }

  if (error) {
    return (
      <div className="space-y-6">
        <SettingsSection title={t('title')} description={t('description')}>
          <div className="flex flex-col items-center gap-3 py-8 text-muted-foreground">
            <IconAlertCircle className="text-destructive w-8 h-8" />
            <span className="text-sm text-center">{error}</span>
            <button onClick={fetchData} className="flex items-center gap-1.5 text-xs text-primary hover:underline">
              <IconRefresh className="w-3 h-3" />
              {t('retry')}
            </button>
          </div>
        </SettingsSection>
      </div>
    );
  }

  if (!stats) return null;

  return localizeReactNode(
    <div className="space-y-6">
      <BudgetPolicySection />
      <MemoryGuardianCard />
      <SettingsSection
        title={t('title')}
        description={t('description')}
        action={
          <button
            onClick={fetchData}
            className="p-2 rounded-lg hover:bg-accent transition-colors text-muted-foreground hover:text-foreground"
            title={t('refresh')}
          >
            <IconRefresh className="w-4 h-4" />
          </button>
        }
      >
        {/* Overview cards */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <StatCard
            icon={IconChart}
            label={t('totalTokens')}
            value={formatTokenCount(stats.totalTokens)}
            colorClass="bg-primary/15 text-primary"
          />
          <StatCard
            icon={IconArrowRight}
            label={t('inputTokens')}
            value={formatTokenCount(stats.inputTokens)}
            colorClass="bg-blue-100 dark:bg-blue-900/40 text-blue-600 dark:text-blue-400"
          />
          <StatCard
            icon={() => <IconArrowRight className="w-4 h-4 rotate-90" />}
            label={t('outputTokens')}
            value={formatTokenCount(stats.outputTokens)}
            colorClass="bg-purple-100 dark:bg-purple-900/40 text-purple-600 dark:text-purple-400"
          />
          <StatCard
            icon={IconChart}
            label={t('totalCost')}
            value={formatCost(stats.costUsd)}
            colorClass="bg-emerald-100 dark:bg-emerald-900/40 text-emerald-600 dark:text-emerald-400"
          />
        </div>

        {/* Secondary stats */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mt-3">
          <StatCard
            icon={IconDatabase}
            label={t('cacheHitRate')}
            value={`${(stats.cacheHitRate * 100).toFixed(1)}%`}
            subValue={formatTokenCount(stats.cachedTokens)}
            colorClass="bg-emerald-100 dark:bg-emerald-900/40 text-emerald-600 dark:text-emerald-400"
          />
          <StatCard
            icon={IconDatabase}
            label={t('cacheSavings') || 'Cache Savings'}
            value={formatCost(stats.cacheSavingsUsd || 0)}
            colorClass="bg-emerald-100 dark:bg-emerald-900/40 text-emerald-600 dark:text-emerald-400"
          />
          <StatCard
            icon={IconBrain}
            label={t('reasoningTokens')}
            value={formatTokenCount(stats.reasoningTokens)}
            colorClass="bg-amber-100 dark:bg-amber-900/40 text-amber-600 dark:text-amber-400"
          />
          <StatCard
            icon={IconChat}
            label={t('totalCalls')}
            value={stats.calls.toLocaleString()}
            colorClass="bg-sky-100 dark:bg-sky-900/40 text-sky-600 dark:text-sky-400"
          />
        </div>
      </SettingsSection>

      {/* Daily trend */}
      <SettingsSection title={t('trendsTitle')}>
        <DailyChart data={daily} t={t} />
      </SettingsSection>

      {/* Routing analytics (conditional) */}
      {stats.routingBreakdown && Object.keys(stats.routingBreakdown).length > 0 && (
        <SettingsSection title={t('routingTitle')}>
          <RoutingAnalyticsPanel stats={stats} t={t} />
        </SettingsSection>
      )}

      {/* Privacy route analytics (conditional) */}
      {stats.privacyRouteBreakdown && Object.keys(stats.privacyRouteBreakdown).length > 0 && (
        <SettingsSection title={t('privacyRoutingTitle')}>
          <PrivacyRoutePanel breakdown={stats.privacyRouteBreakdown} t={t} />
        </SettingsSection>
      )}

      {/* Model breakdown + Sessions */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <SettingsSection title={t('modelsTitle')}>
          <ModelBreakdown stats={stats} t={t} timeRange={timeRange} onSelectSession={setSelectedSessionId} />
        </SettingsSection>

        <SettingsSection title={t('sessionsTitle')}>
          <SessionTable sessions={sessions} t={t} onSelectSession={setSelectedSessionId} />
        </SettingsSection>
      </div>

      {/* Global Activity Patterns */}
      <SettingsSection title={t('activityTitle')}>
        {activity && activity.active_days > 0 ? (
          <div className="space-y-6">
            {/* Time Range Selector */}
            <div className="flex items-center gap-2 pb-2 border-b border-border/50">
              <button
                onClick={() => setTimeRange(7)}
                className={`px-4 py-1.5 text-sm font-medium rounded-full transition-colors ${
                  timeRange === 7
                    ? 'bg-primary text-primary-foreground'
                    : 'text-muted-foreground hover:text-foreground hover:bg-muted'
                }`}
              >
                7 Days / 7天
              </button>
              <button
                onClick={() => setTimeRange(30)}
                className={`px-4 py-1.5 text-sm font-medium rounded-full transition-colors ${
                  timeRange === 30
                    ? 'bg-primary text-primary-foreground'
                    : 'text-muted-foreground hover:text-foreground hover:bg-muted'
                }`}
              >
                30 Days / 30天
              </button>
              <button
                onClick={() => setTimeRange(365)}
                className={`px-4 py-1.5 text-sm font-medium rounded-full transition-colors ${
                  timeRange === 365
                    ? 'bg-primary text-primary-foreground'
                    : 'text-muted-foreground hover:text-foreground hover:bg-muted'
                }`}
              >
                All / 全部
              </button>
            </div>

            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <StatCard
                icon={IconChart}
                label={t('activeDays')}
                value={activity.active_days.toString()}
                colorClass="bg-blue-100 dark:bg-blue-900/40 text-blue-600 dark:text-blue-400"
              />
              <StatCard
                icon={IconChart}
                label={t('maxStreak')}
                value={`${activity.max_streak} days`}
                colorClass="bg-green-100 dark:bg-green-900/40 text-green-600 dark:text-green-400"
              />
              <StatCard
                icon={IconChat}
                label={t('busiestDay')}
                value={['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'][activity.busiest_day_of_week]}
                colorClass="bg-purple-100 dark:bg-purple-900/40 text-purple-600 dark:text-purple-400"
              />
              <StatCard
                icon={IconChart}
                label={t('busiestHour')}
                value={`${activity.busiest_hour}:00`}
                colorClass="bg-orange-100 dark:bg-orange-900/40 text-orange-600 dark:text-orange-400"
              />
            </div>

            {/* Daily Trend Chart */}
            {activity.daily_activities && activity.daily_activities.length > 0 && (
              <div className="space-y-2">
                <div className="flex items-center gap-2 text-sm font-medium text-foreground">
                  <IconChart className="w-4 h-4 text-primary" />
                  {t('dailyTrendActivity')}
                </div>
                <ActivityDailyChart data={activity.daily_activities} />
              </div>
            )}

            {/* Week Distribution Bar Chart */}
            <div className="space-y-2">
              <div className="flex items-center gap-2 text-sm font-medium text-foreground">
                <IconChart className="w-4 h-4 text-primary" />
                {t('weekDistribution')}
              </div>
              <WeekDistributionChart data={activity.by_day_of_week} />
            </div>

            {/* Hour Distribution Line Chart */}
            <div className="space-y-2">
              <div className="flex items-center gap-2 text-sm font-medium text-foreground">
                <IconChart className="w-4 h-4 text-primary" />
                {t('hourDistribution')}
              </div>
              <HourDistributionChart data={activity.by_hour} />
            </div>
          </div>
        ) : (
          <div className="flex flex-col items-center gap-3 py-12 text-muted-foreground">
            <IconChart className="w-12 h-12 text-muted-foreground/30" />
            <div className="text-center">
              <p className="text-sm font-medium">{t('noActivityTitle')}</p>
              <p className="text-xs mt-1">{t('noActivityDesc')}</p>
            </div>
          </div>
        )}
      </SettingsSection>

      {/* Top Sessions (A3) */}
      <SettingsSection title={t('topSessionsTitle')}>
        {topSessions && topSessions.length > 0 ? (
          <div className="space-y-6">
            {/* Metric Selector */}
            <div className="flex items-center gap-2 pb-2 border-b border-border/50">
              {(['duration', 'messages', 'tokens', 'tool_calls'] as const).map((m) => {
                const metricLabels = {
                  duration: t('metricDuration'),
                  messages: t('metricMessages'),
                  tokens: t('metricTokens'),
                  tool_calls: t('metricToolCalls'),
                };
                const isActive = topSessionMetric === m;
                return (
                  <button
                    key={m}
                    onClick={() => setTopSessionMetric(m)}
                    className={cn(
                      'px-3 py-1.5 text-xs font-medium rounded-lg transition-all',
                      isActive
                        ? 'bg-primary/10 text-primary border border-primary/20'
                        : 'text-muted-foreground hover:bg-accent hover:text-foreground border border-transparent',
                    )}
                  >
                    {metricLabels[m]}
                  </button>
                );
              })}
            </div>

            {/* Top Sessions List */}
            <div className="space-y-3">
              {topSessions.map((session, idx) => {
                const duration = Math.floor(session.duration_ms / 60000);
                const metricDisplay = {
                  duration: `${duration}min`,
                  messages: `${session.message_count}`,
                  tokens: `${formatTokenCount(session.total_tokens)}`,
                  tool_calls: `${session.tool_calls}`,
                }[topSessionMetric];

                return (
                  <motion.div
                    key={session.session_id}
                    initial={{ opacity: 0, y: 10 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: idx * 0.05 }}
                    className="flex items-center gap-4 p-4 rounded-xl bg-background/60 border border-border/40 hover:border-primary/40 hover:bg-background/80 transition-all"
                  >
                    {/* Rank Badge */}
                    <div className="flex-shrink-0 w-8 h-8 rounded-full bg-primary/10 flex items-center justify-center">
                      <span className="text-sm font-bold text-primary">#{idx + 1}</span>
                    </div>

                    {/* Session Info */}
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 mb-1">
                        <span className="text-xs font-mono text-muted-foreground truncate">
                          {session.session_id.substring(0, 12)}...
                        </span>
                        <span className="text-xs text-muted-foreground">
                          {new Date(session.started_at * 1000).toLocaleDateString()}
                        </span>
                      </div>
                      <div className="flex items-center gap-3 text-xs text-muted-foreground">
                        <span className="inline-flex items-center gap-1">
                          <IconClock className="w-3.5 h-3.5" /> {duration}min
                        </span>
                        <span className="inline-flex items-center gap-1">
                          <IconChat className="w-3.5 h-3.5" /> {session.message_count}
                        </span>
                        <span className="inline-flex items-center gap-1">
                          <IconTarget className="w-3.5 h-3.5" /> {session.tool_calls}
                        </span>
                        <span className="inline-flex items-center gap-1">
                          <IconChart className="w-3.5 h-3.5" /> {formatTokenCount(session.total_tokens)}
                        </span>
                      </div>
                    </div>

                    {/* Metric Value */}
                    <div className="flex-shrink-0 text-right">
                      <div className="text-2xl font-bold text-primary">{metricDisplay}</div>
                      <div className="text-xs text-muted-foreground capitalize">{topSessionMetric}</div>
                    </div>
                  </motion.div>
                );
              })}
            </div>
          </div>
        ) : (
          <div className="flex flex-col items-center gap-3 py-12 text-muted-foreground">
            <IconChat className="w-12 h-12 text-muted-foreground/30" />
            <div className="text-center">
              <p className="text-sm font-medium">{t('noTopSessionsTitle')}</p>
              <p className="text-xs mt-1">{t('noTopSessionsDesc')}</p>
            </div>
          </div>
        )}
      </SettingsSection>

      {/* Session Analytics Dialog */}
      {selectedSessionId && (
        <SessionAnalyticsDialog sessionId={selectedSessionId} onClose={() => setSelectedSessionId(null)} />
      )}
    </div>,
    locale,
  );
}

export default UsageStatisticsSection;
