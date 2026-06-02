'use client';

import { memo } from 'react';
import { IconChart, IconZap, IconCpu, IconGlow } from '@/components/ui/icons/PremiumIcons';
import { Navigation } from 'lucide-react';
import { cn } from '@/lib/utils/classnameUtils';
import type { UsageStats } from '@/services/statistics';

export function formatTokenCount(count: number | undefined | null): string {
  if (count == null) return '0';
  if (count >= 1_000_000) return `${(count / 1_000_000).toFixed(1)}M`;
  if (count >= 1_000) return `${(count / 1_000).toFixed(1)}k`;
  return count.toLocaleString();
}

export function formatCost(cost: number | undefined | null): string {
  if (cost == null || cost === 0) return '$0.00';
  if (cost < 0.01) return `$${cost.toFixed(4)}`;
  return `$${cost.toFixed(2)}`;
}

const TIER_CONFIG = {
  simple: {
    icon: IconZap,
    colorClass: 'bg-emerald-100 dark:bg-emerald-900/40 text-emerald-600 dark:text-emerald-400',
    barColor: 'bg-emerald-500',
  },
  standard: {
    icon: IconCpu,
    colorClass: 'bg-blue-100 dark:bg-blue-900/40 text-blue-600 dark:text-blue-400',
    barColor: 'bg-blue-500',
  },
  reasoning: {
    icon: IconGlow,
    colorClass: 'bg-purple-100 dark:bg-purple-900/40 text-purple-600 dark:text-purple-400',
    barColor: 'bg-purple-500',
  },
} as const;

const TIER_ORDER: (keyof typeof TIER_CONFIG)[] = ['simple', 'standard', 'reasoning'];

interface RoutingAnalyticsProps {
  stats: UsageStats;
  t: (key: string, params?: Record<string, string | number>) => string;
}

const RoutingAnalyticsPanel = memo<RoutingAnalyticsProps>(({ stats, t }) => {
  const { routingBreakdown, estimatedSavings } = stats;
  if (!routingBreakdown || Object.keys(routingBreakdown).length === 0) return null;

  const totalRoutedCalls = Object.values(routingBreakdown).reduce((s, v) => s + v.calls, 0);

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2 text-sm font-medium text-foreground">
        <Navigation className="w-4 h-4 text-primary" />
        {t('routingDistribution')}
      </div>

      {estimatedSavings && (
        <div className="flex items-center gap-3 p-3 rounded-xl bg-emerald-50 dark:bg-emerald-950/30 border border-emerald-200/50 dark:border-emerald-800/30">
          <div className="w-10 h-10 rounded-lg flex items-center justify-center bg-emerald-100 dark:bg-emerald-900/50 text-emerald-600 dark:text-emerald-400 shrink-0">
            <IconChart className="w-5 h-5" />
          </div>
          <div className="flex-1 min-w-0">
            <div className="text-sm font-bold text-emerald-700 dark:text-emerald-300">
              {t('estimatedSavings')}: {formatCost(estimatedSavings.savings)}
              <span className="text-xs font-normal ml-1.5 text-emerald-600/70 dark:text-emerald-400/60">
                ({estimatedSavings.savingsPercent.toFixed(1)}%)
              </span>
            </div>
            <div className="text-[10px] text-emerald-600/70 dark:text-emerald-400/60 mt-0.5">
              {t('savingsDescription')}
            </div>
          </div>
        </div>
      )}

      {/* Distribution bar */}
      {totalRoutedCalls > 0 && (
        <div className="h-3 rounded-full overflow-hidden flex bg-border/30">
          {TIER_ORDER.map((tier) => {
            const data = routingBreakdown[tier];
            if (!data || data.calls === 0) return null;
            const pct = (data.calls / totalRoutedCalls) * 100;
            return (
              <div
                key={tier}
                className={cn('h-full transition-all', TIER_CONFIG[tier].barColor)}
                style={{ width: `${pct}%` }}
                title={`${t(`tier${tier.charAt(0).toUpperCase()}${tier.slice(1)}`)}: ${data.calls} (${pct.toFixed(1)}%)`}
              />
            );
          })}
        </div>
      )}

      {/* Per-tier cards */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        {TIER_ORDER.map((tier) => {
          const data = routingBreakdown[tier];
          if (!data) return null;
          const cfg = TIER_CONFIG[tier];
          const Icon = cfg.icon;
          const pct = totalRoutedCalls > 0 ? Math.round((data.calls / totalRoutedCalls) * 100) : 0;
          const tierKey = `tier${tier.charAt(0).toUpperCase()}${tier.slice(1)}`;

          return (
            <div key={tier} className="flex flex-col gap-2 p-3 rounded-xl bg-background/60 border border-border/40">
              <div className="flex items-center gap-2">
                <div className={cn('w-7 h-7 rounded-lg flex items-center justify-center', cfg.colorClass)}>
                  <Icon className="w-3.5 h-3.5" />
                </div>
                <span className="text-xs font-medium text-foreground">{t(tierKey)}</span>
                <span className="text-[10px] text-muted-foreground ml-auto">{pct}%</span>
              </div>
              <div className="text-xs text-muted-foreground space-y-0.5">
                <div>{t('tierCalls', { count: data.calls })}</div>
                <div>{formatTokenCount(data.totalTokens)} tokens</div>
                {data.costUsd > 0 && <div>{formatCost(data.costUsd)}</div>}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
});
RoutingAnalyticsPanel.displayName = 'RoutingAnalyticsPanel';

export default RoutingAnalyticsPanel;
