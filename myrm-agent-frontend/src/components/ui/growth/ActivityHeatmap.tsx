'use client';

import { useMemo } from 'react';
import { useTranslations } from 'next-intl';
import { cn } from '@/lib/utils/classnameUtils';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip';
import type { ActivityDay } from '@/services/statistics';

interface ActivityHeatmapProps {
  data: ActivityDay[];
}

const WEEKS = 12;
const DAYS_PER_WEEK = 7;

function getIntensityClass(count: number, maxCount: number): string {
  if (count === 0) return 'bg-muted/40';
  const ratio = count / Math.max(maxCount, 1);
  if (ratio >= 0.75) return 'bg-emerald-500';
  if (ratio >= 0.5) return 'bg-emerald-400';
  if (ratio >= 0.25) return 'bg-emerald-300 dark:bg-emerald-400/60';
  return 'bg-emerald-200 dark:bg-emerald-500/30';
}

export default function ActivityHeatmap({ data }: ActivityHeatmapProps) {
  const t = useTranslations('growthDashboard.activityHeatmap');

  const { grid, maxCount } = useMemo(() => {
    const countMap = new Map<string, number>();
    let max = 0;
    for (const d of data) {
      countMap.set(d.date, d.count);
      if (d.count > max) max = d.count;
    }

    const today = new Date();
    const totalDays = WEEKS * DAYS_PER_WEEK;
    const cells: { date: string; count: number; dayOfWeek: number }[] = [];

    for (let i = totalDays - 1; i >= 0; i--) {
      const d = new Date(today);
      d.setDate(d.getDate() - i);
      const key = d.toISOString().slice(0, 10);
      cells.push({
        date: key,
        count: countMap.get(key) ?? 0,
        dayOfWeek: d.getDay(),
      });
    }

    return { grid: cells, maxCount: max };
  }, [data]);

  const weeks: { date: string; count: number; dayOfWeek: number }[][] = [];
  for (let w = 0; w < WEEKS; w++) {
    weeks.push(grid.slice(w * DAYS_PER_WEEK, (w + 1) * DAYS_PER_WEEK));
  }

  return (
    <div className="space-y-2">
      <div className="flex gap-[3px] overflow-x-auto pb-1">
        {weeks.map((week, wi) => (
          <div key={wi} className="flex flex-col gap-[3px]">
            {week.map((cell) => (
              <Tooltip key={cell.date}>
                <TooltipTrigger asChild>
                  <div
                    className={cn(
                      'w-3 h-3 md:w-3.5 md:h-3.5 rounded-sm transition-colors',
                      getIntensityClass(cell.count, maxCount),
                    )}
                  />
                </TooltipTrigger>
                <TooltipContent side="top" className="text-xs">
                  <span className="font-medium">{cell.date}</span>
                  <span className="ml-1.5 text-muted-foreground">
                    {cell.count === 1 ? t('session', { count: cell.count }) : t('sessions', { count: cell.count })}
                  </span>
                </TooltipContent>
              </Tooltip>
            ))}
          </div>
        ))}
      </div>

      {/* Legend */}
      <div className="flex items-center justify-end gap-1.5 text-xs text-muted-foreground">
        <span>{t('less')}</span>
        <div className="w-3 h-3 rounded-sm bg-muted/40" />
        <div className="w-3 h-3 rounded-sm bg-emerald-200 dark:bg-emerald-500/30" />
        <div className="w-3 h-3 rounded-sm bg-emerald-300 dark:bg-emerald-400/60" />
        <div className="w-3 h-3 rounded-sm bg-emerald-400" />
        <div className="w-3 h-3 rounded-sm bg-emerald-500" />
        <span>{t('more')}</span>
      </div>
    </div>
  );
}
