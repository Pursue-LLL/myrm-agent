'use client';

import { memo } from 'react';
import { useTranslations } from 'next-intl';
import { Layers, PlayCircle, PauseCircle, AlertCircle } from 'lucide-react';
import { cn } from '@/lib/utils/classnameUtils';
import type { StatusFilter } from './cron-utils';

interface StatCard {
  key: StatusFilter;
  icon: React.ElementType;
  labelKey: string;
  colorClass: string;
  bgClass: string;
}

const STAT_CARDS: StatCard[] = [
  {
    key: 'all',
    icon: Layers,
    labelKey: 'statsTotal',
    colorClass: 'text-blue-600 dark:text-blue-400',
    bgClass: 'bg-blue-500/10',
  },
  {
    key: 'active',
    icon: PlayCircle,
    labelKey: 'statsActive',
    colorClass: 'text-green-600 dark:text-green-400',
    bgClass: 'bg-green-500/10',
  },
  {
    key: 'paused',
    icon: PauseCircle,
    labelKey: 'statsPaused',
    colorClass: 'text-muted-foreground',
    bgClass: 'bg-muted/50',
  },
  {
    key: 'error',
    icon: AlertCircle,
    labelKey: 'statsError',
    colorClass: 'text-destructive',
    bgClass: 'bg-destructive/10',
  },
];

interface CronStatsBarProps {
  stats: { total: number; active: number; paused: number; errored: number };
  activeFilter: StatusFilter;
  onFilterChange: (filter: StatusFilter) => void;
}

function getCount(stats: CronStatsBarProps['stats'], key: StatusFilter): number {
  if (key === 'all') return stats.total;
  if (key === 'active') return stats.active;
  if (key === 'paused') return stats.paused;
  return stats.errored;
}

const CronStatsBar = memo<CronStatsBarProps>(({ stats, activeFilter, onFilterChange }) => {
  const t = useTranslations('cron');

  return (
    <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
      {STAT_CARDS.map(({ key, icon: Icon, labelKey, colorClass, bgClass }) => {
        const isActive = activeFilter === key;
        const count = getCount(stats, key);

        return (
          <button
            key={key}
            onClick={() => onFilterChange(isActive ? 'all' : key)}
            className={cn(
              'flex items-center gap-3 rounded-lg border px-3 py-2.5 transition-all text-left',
              'hover:bg-accent/50',
              isActive && 'ring-2 ring-primary/30 bg-accent/30',
            )}
          >
            <div className={cn('rounded-full p-1.5', bgClass)}>
              <Icon className={cn('h-4 w-4', colorClass)} />
            </div>
            <div className="min-w-0">
              <p className="text-xs text-muted-foreground truncate">{t(labelKey)}</p>
              <p className="text-lg font-semibold leading-tight">{count}</p>
            </div>
          </button>
        );
      })}
    </div>
  );
});

CronStatsBar.displayName = 'CronStatsBar';
export default CronStatsBar;
