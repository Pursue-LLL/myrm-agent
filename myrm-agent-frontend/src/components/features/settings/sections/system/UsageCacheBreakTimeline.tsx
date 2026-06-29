'use client';

import { memo } from 'react';
import { IconAlertCircle } from '@/components/features/icons/PremiumIcons';
import { type DailyUsage } from '@/services/statistics';
import { cn } from '@/lib/utils/classnameUtils';

export const CacheBreakTimeline = memo<{ data: DailyUsage[]; t: ReturnType<typeof import('next-intl').useTranslations> }>(
  ({ data, t }) => {
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
  },
);
CacheBreakTimeline.displayName = 'CacheBreakTimeline';
