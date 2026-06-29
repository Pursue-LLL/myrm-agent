'use client';

import { memo } from 'react';
import { motion } from 'framer-motion';
import { IconChart } from '@/components/features/icons/PremiumIcons';
import { formatTokenCount } from './RoutingAnalyticsPanel';
import { type DailyUsage } from '@/services/statistics';
import { CacheBreakTimeline } from './UsageCacheBreakTimeline';

const GRID_LINES = [0.25, 0.5, 0.75] as const;

function getLabelIndices(len: number): Set<number> {
  if (len <= 7) return new Set(Array.from({ length: len }, (_, i) => i));
  const step = Math.ceil(len / 5);
  const indices = new Set<number>();
  for (let i = 0; i < len; i += step) indices.add(i);
  indices.add(len - 1);
  return indices;
}

export const DailyChart = memo<{ data: DailyUsage[]; t: ReturnType<typeof import('next-intl').useTranslations> }>(
  ({ data, t }) => {
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

              <svg viewBox="0 0 100 100" preserveAspectRatio="none" className="absolute inset-0 w-full h-full pointer-events-none">
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
  },
);
DailyChart.displayName = 'DailyChart';
