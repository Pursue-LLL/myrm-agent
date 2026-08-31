'use client';

import { useTranslations } from 'next-intl';
import { Badge } from '@/components/primitives/badge';
import { cn } from '@/lib/utils/classnameUtils';
import type { SkillHealthItem } from '@/services/statistics';

const STATUS_VARIANT: Record<string, string> = {
  STAR: 'bg-amber-500/15 text-amber-700 dark:text-amber-300 border-amber-500/30',
  HEALTHY: 'bg-emerald-500/15 text-emerald-700 dark:text-emerald-300 border-emerald-500/30',
  AT_RISK: 'bg-red-500/15 text-red-700 dark:text-red-300 border-red-500/30',
  STALE: 'bg-muted text-muted-foreground border-border',
};

interface SkillHealthPanelProps {
  items: SkillHealthItem[];
}

export default function SkillHealthPanel({ items }: SkillHealthPanelProps) {
  const t = useTranslations('growthDashboard.skillHealth');

  if (items.length === 0) {
    return <p className="text-sm text-muted-foreground py-2">{t('empty')}</p>;
  }

  const activeItems = items.filter((item) => item.call_count_total > 0 || item.call_count_7d > 0);
  const displayItems = (activeItems.length > 0 ? activeItems : items).slice(0, 8);

  return (
    <div className="space-y-2">
      {displayItems.map((item) => (
        <div
          key={item.skill_name}
          className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 rounded-lg border border-border/60 px-3 py-2.5"
        >
          <div className="min-w-0">
            <p className="text-sm font-medium truncate">{item.skill_name}</p>
            <p className="text-xs text-muted-foreground mt-0.5">
              {t('calls7d', { count: item.call_count_7d })}
              {' · '}
              {t('successRate', { rate: Math.round(item.success_rate_7d * 100) })}
            </p>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            <span className="text-sm font-semibold tabular-nums">{Math.round(item.health_score)}</span>
            <Badge variant="outline" className={cn('text-xs', STATUS_VARIANT[item.status] ?? STATUS_VARIANT.STALE)}>
              {t(`status.${item.status}`, { default: item.status })}
            </Badge>
          </div>
        </div>
      ))}
    </div>
  );
}
