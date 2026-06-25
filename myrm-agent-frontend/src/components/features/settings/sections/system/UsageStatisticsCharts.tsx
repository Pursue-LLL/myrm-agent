'use client';

import { memo, useEffect, useState } from 'react';
import { motion } from 'framer-motion';
import {
  IconChat,
  IconAlertCircle,
  IconChart,
} from '@/components/features/icons/PremiumIcons';
import { formatTokenCount, formatCost } from './RoutingAnalyticsPanel';
import { type DailyUsage, type SessionUsage } from '@/services/statistics';
import { cn } from '@/lib/utils/classnameUtils';

export { ModelBreakdown } from './UsageModelBreakdown';

/* ─── StatCard ─── */

interface StatCardProps {
  icon: React.ElementType;
  label: string;
  value: string;
  subValue?: string;
  colorClass: string;
}

export const StatCard = memo<StatCardProps>(({ icon: Icon, label, value, subValue, colorClass }) => (
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

/* ─── CacheBreakTimeline ─── */

export const CacheBreakTimeline = memo<{ data: DailyUsage[]; t: ReturnType<typeof import('next-intl').useTranslations> }>(({ data, t }) => {
  const hasBreaks = data.some((d) => Object.keys(d.cacheBreakCounts || {}).length > 0);
  if (!hasBreaks) return null;

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

/* ─── DailyChart ─── */

const GRID_LINES = [0.25, 0.5, 0.75] as const;

function getLabelIndices(len: number): Set<number> {
  if (len <= 7) return new Set(Array.from({ length: len }, (_, i) => i));
  const step = Math.ceil(len / 5);
  const indices = new Set<number>();
  for (let i = 0; i < len; i += step) indices.add(i);
  indices.add(len - 1);
  return indices;
}

export const DailyChart = memo<{ data: DailyUsage[]; t: ReturnType<typeof import('next-intl').useTranslations> }>(({ data, t }) => {
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
        <div className="flex flex-col justify-between shrink-0 w-10 text-[9px] tabular-nums text-muted-foreground/50 text-right h-40">
          <span>{formatTokenCount(maxTokens)}</span>
          <span>{formatTokenCount(maxTokens * 0.5)}</span>
          <span>0</span>
        </div>

        <div className="flex-1 min-w-0">
          <div className="relative h-40 rounded-lg overflow-hidden">
            <div className="absolute inset-0 bg-gradient-to-t from-muted/30 to-transparent pointer-events-none" />

            {GRID_LINES.map((ratio) => (
              <div
                key={ratio}
                className="absolute left-0 right-0 border-t border-dashed border-border/25"
                style={{ bottom: `${ratio * 100}%` }}
              />
            ))}
            <div className="absolute bottom-0 left-0 right-0 h-px bg-border/40" />

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

                    <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 hidden group-hover:block z-20 pointer-events-none">
                      <div className="bg-popover/95 backdrop-blur-sm border border-border/50 rounded-lg shadow-lg px-3 py-2 text-[10px] whitespace-nowrap">
                        <div className="font-medium text-foreground mb-1">{d.date.slice(5)}</div>
                        <div className="text-muted-foreground">
                          {formatTokenCount(d.totalTokens)} tokens
                          {cacheRate !== null && (
                            <span className="ml-1.5 text-emerald-600 dark:text-emerald-400">({cacheRate}% cached)</span>
                          )}
                        </div>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>

            <svg viewBox={`0 0 100 100`} preserveAspectRatio="none" className="absolute inset-0 w-full h-full pointer-events-none">
              <motion.polyline
                initial={{ pathLength: 0 }}
                animate={{ pathLength: 1 }}
                transition={{ duration: 1, delay: 0.5 }}
                points={points}
                fill="none"
                stroke="rgb(16 185 129)"
                strokeWidth="1.5"
                vectorEffect="non-scaling-stroke"
                className="drop-shadow-sm"
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

        <div className="flex flex-col justify-between shrink-0 w-8 text-[9px] tabular-nums text-emerald-600/70 dark:text-emerald-400/70 text-left h-40">
          <span>100%</span>
          <span>50%</span>
          <span>0%</span>
        </div>
      </div>

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

      <CacheBreakTimeline data={data} t={t} />
    </div>
  );
});
DailyChart.displayName = 'DailyChart';

/* ─── SessionTable ─── */

export const SessionTable = memo<{
  sessions: SessionUsage[];
  t: ReturnType<typeof import('next-intl').useTranslations>;
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

/* ─── WeekDistributionChart ─── */

export const WeekDistributionChart = memo<{ data: Record<number, number> }>(({ data }) => {
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

/* ─── ActivityDailyChart ─── */

export const ActivityDailyChart = memo<{ data: Array<{ date: string; tool_calls: number }> }>(({ data }) => {
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

/* ─── HourDistributionChart ─── */

export const HourDistributionChart = memo<{ data: Record<number, number> }>(({ data }) => {
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

/* ─── PrivacyRoutePanel ─── */

export const PrivacyRoutePanel = memo<{
  breakdown: Record<string, number>;
  t: ReturnType<typeof import('next-intl').useTranslations>;
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
