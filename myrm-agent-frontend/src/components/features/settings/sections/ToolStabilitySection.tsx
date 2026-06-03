'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import { useLocale, useTranslations } from 'next-intl';
import {
  IconActivity,
  IconAlertCircle,
  IconRefresh,
  IconClock,
  IconWrench,
  IconXCircle,
} from '@/components/features/icons/PremiumIcons';
import SettingsSection from './SettingsSection';
import { Button } from '@/components/primitives/button';
import { getToolStability, type ToolStabilityAnalytics } from '@/services/statistics';
import { cn } from '@/lib/utils/classnameUtils';

function formatPercent(locale: string, value: number): string {
  return new Intl.NumberFormat(locale, {
    style: 'percent',
    maximumFractionDigits: 2,
  }).format(value);
}

function formatCount(locale: string, value: number): string {
  return new Intl.NumberFormat(locale, { maximumFractionDigits: 0 }).format(value);
}

function formatMs(locale: string, value: number): string {
  return new Intl.NumberFormat(locale, { maximumFractionDigits: 0 }).format(value);
}

export default function ToolStabilitySection() {
  const t = useTranslations('settings.toolStabilitySection');
  const locale = useLocale();
  const [data, setData] = useState<ToolStabilityAnalytics | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await getToolStability(undefined, 30);
      setData(res);
    } catch {
      setError('loadError');
      setData(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const tableRows = useMemo(() => {
    if (!data?.daily_stability?.length) return [];
    return [...data.daily_stability]
      .sort((a, b) => b.date.localeCompare(a.date) || b.tool_name.localeCompare(a.tool_name))
      .slice(0, 40);
  }, [data]);

  const statCards = useMemo(
    () => [
      {
        icon: IconActivity,
        label: t('totalCalls'),
        value: data ? formatCount(locale, data.global_total_calls) : '—',
        className: 'bg-primary/10 text-primary',
      },
      {
        icon: IconXCircle,
        label: t('failureRate'),
        value: data ? formatPercent(locale, data.global_failure_rate) : '—',
        className: 'bg-destructive/10 text-destructive',
      },
      {
        icon: IconClock,
        label: t('avgDuration'),
        value: data ? `${formatMs(locale, data.global_avg_duration_ms)} \u00a0ms` : '—',
        className: 'bg-violet-500/10 text-violet-600 dark:text-violet-400',
      },
      {
        icon: IconWrench,
        label: t('busiestTool'),
        value: data?.busiest_tool || t('none'),
        className: 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400',
      },
      {
        icon: IconAlertCircle,
        label: t('mostFailedTool'),
        value: data?.most_failed_tool || t('none'),
        className: 'bg-amber-500/10 text-amber-700 dark:text-amber-300',
      },
    ],
    [data, locale, t],
  );

  return (
    <div className="w-full max-w-5xl">
      <SettingsSection
        title={t('title')}
        description={t('description')}
        action={
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="gap-1.5 shrink-0"
            onClick={() => void load()}
            disabled={loading}
            aria-label={t('refresh')}
          >
            <IconRefresh className={cn('h-4 w-4', loading && 'animate-spin')} aria-hidden />
            <span className="hidden sm:inline">{t('refresh')}</span>
          </Button>
        }
      >
        {error && (
          <div
            role="alert"
            className="flex flex-col sm:flex-row sm:items-center gap-3 rounded-xl border border-destructive/40 bg-destructive/5 px-4 py-3 text-sm text-destructive"
          >
            <div className="flex items-center gap-2 min-w-0">
              <IconAlertCircle className="h-4 w-4 shrink-0" aria-hidden />
              <span className="break-words">{t('loadError')}</span>
            </div>
            <Button
              type="button"
              variant="secondary"
              size="sm"
              className="shrink-0 w-full sm:w-auto"
              onClick={() => void load()}
            >
              {t('retry')}
            </Button>
          </div>
        )}

        {loading && !data && !error && (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
            {Array.from({ length: 5 }).map((_, i) => (
              <div key={i} className="h-24 rounded-xl border border-border/40 bg-muted/20 animate-pulse" />
            ))}
          </div>
        )}

        {data && (
          <>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
              {statCards.map((card) => {
                const Icon = card.icon;
                return (
                  <div
                    key={card.label}
                    className="flex flex-col gap-2 p-4 rounded-xl bg-background/60 border border-border/40"
                  >
                    <div className="flex items-center gap-2 min-w-0">
                      <div
                        className={cn('w-9 h-9 rounded-lg flex items-center justify-center shrink-0', card.className)}
                      >
                        <Icon className="h-4 w-4" aria-hidden />
                      </div>
                      <span className="text-xs text-muted-foreground font-medium leading-snug line-clamp-2">
                        {card.label}
                      </span>
                    </div>
                    <p
                      className="text-base sm:text-lg font-semibold tabular-nums text-foreground break-all"
                      title={typeof card.value === 'string' ? card.value : undefined}
                    >
                      {card.value}
                    </p>
                  </div>
                );
              })}
            </div>

            <div className="space-y-2">
              <h3 className="text-sm font-medium text-foreground">{t('tableTitle')}</h3>
              {tableRows.length === 0 ? (
                <p className="text-sm text-muted-foreground py-6 text-center border border-dashed border-border/60 rounded-xl">
                  {t('noData')}
                </p>
              ) : (
                <div className="overflow-x-auto rounded-xl border border-border/50 bg-background/40">
                  <table className="w-full min-w-[640px] text-sm text-left">
                    <thead>
                      <tr className="border-b border-border/50 bg-secondary/20">
                        <th className="p-3 font-medium text-muted-foreground whitespace-nowrap">{t('columns.date')}</th>
                        <th className="p-3 font-medium text-muted-foreground whitespace-nowrap">{t('columns.tool')}</th>
                        <th className="p-3 font-medium text-muted-foreground whitespace-nowrap">
                          {t('columns.calls')}
                        </th>
                        <th className="p-3 font-medium text-muted-foreground whitespace-nowrap">
                          {t('columns.success')}
                        </th>
                        <th className="p-3 font-medium text-muted-foreground whitespace-nowrap">
                          {t('columns.failures')}
                        </th>
                        <th className="p-3 font-medium text-muted-foreground whitespace-nowrap">
                          {t('columns.failRate')}
                        </th>
                        <th className="p-3 font-medium text-muted-foreground whitespace-nowrap">
                          {t('columns.avgMs')}
                        </th>
                        <th className="p-3 font-medium text-muted-foreground whitespace-nowrap">
                          {t('columns.p90Ms')}
                        </th>
                      </tr>
                    </thead>
                    <tbody>
                      {tableRows.map((row) => (
                        <tr
                          key={`${row.date}-${row.tool_name}`}
                          className="border-b border-border/30 last:border-0 hover:bg-secondary/10"
                        >
                          <td className="p-3 text-foreground whitespace-nowrap">{row.date}</td>
                          <td className="p-3 text-foreground break-all max-w-[200px]">{row.tool_name}</td>
                          <td className="p-3 tabular-nums">{formatCount(locale, row.total_calls)}</td>
                          <td className="p-3 tabular-nums text-emerald-600 dark:text-emerald-400">
                            {formatCount(locale, row.success_count)}
                          </td>
                          <td className="p-3 tabular-nums text-destructive/90">
                            {formatCount(locale, row.failure_count)}
                          </td>
                          <td className="p-3 tabular-nums">{formatPercent(locale, row.failure_rate)}</td>
                          <td className="p-3 tabular-nums">{formatMs(locale, row.avg_duration_ms)}</td>
                          <td className="p-3 tabular-nums">{formatMs(locale, row.p90_duration_ms)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          </>
        )}

        {!loading && !data && !error && <p className="text-sm text-muted-foreground text-center py-8">{t('noData')}</p>}
      </SettingsSection>
    </div>
  );
}
