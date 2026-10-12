'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import { useTranslations } from 'next-intl';
import { Coins, Timer, TrendingUp } from 'lucide-react';
import { Skeleton } from '@/components/primitives/skeleton';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/primitives/table';
import { cn } from '@/lib/utils/classnameUtils';
import { fetchUsageStats, type UsageStatsResponse, type UsageByJob, type UsageByModel } from '@/services/cron';

const PERIOD_OPTIONS = [7, 30, 0] as const;
type Period = (typeof PERIOD_OPTIONS)[number];

function formatTokens(n: number): string {
  if (n >= 1_000_000) {
    return `${(n / 1_000_000).toFixed(1)}M`;
  }
  if (n >= 1_000) {
    return `${(n / 1_000).toFixed(1)}K`;
  }
  return String(n);
}

function pct(part: number, total: number): string {
  if (total === 0) {
    return '0%';
  }
  return `${Math.round((part / total) * 100)}%`;
}

export default function CronUsageStats() {
  const t = useTranslations('cron');
  const [data, setData] = useState<UsageStatsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [period, setPeriod] = useState<Period>(7);

  const load = useCallback(async (days: Period) => {
    setLoading(true);
    try {
      const res = await fetchUsageStats(days);
      setData(res);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load(period);
  }, [period, load]);

  const periodLabel = useMemo(
    () =>
      ({
        7: t('period7d'),
        30: t('period30d'),
        0: t('periodAll'),
      }) as Record<Period, string>,
    [t],
  );

  if (loading) {
    return (
      <div className="space-y-3 p-1">
        <Skeleton className="h-8 w-48 rounded-lg" />
        <Skeleton className="h-16 rounded-lg" />
        <Skeleton className="h-32 rounded-lg" />
      </div>
    );
  }

  if (!data) {
    return null;
  }

  const { summary, by_job, by_model } = data;

  if (summary.total_runs === 0) {
    return (
      <div className="space-y-4 p-1">
        <PeriodSelector period={period} labels={periodLabel} onChange={setPeriod} />
        <div className="text-center py-12 text-muted-foreground">
          <Coins className="h-10 w-10 mx-auto mb-3 opacity-30" />
          <p className="text-sm">{t('noUsageData')}</p>
        </div>
      </div>
    );
  }

  const successRate = Math.round((summary.success_runs / summary.total_runs) * 100);

  return (
    <div className="space-y-4 p-1">
      <PeriodSelector period={period} labels={periodLabel} onChange={setPeriod} />

      <div className="rounded-lg border bg-gradient-to-br from-primary/5 via-card to-card p-4 space-y-3">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b pb-3 border-border/60">
          <div className="flex items-center gap-2.5">
            <div className="h-8 w-8 rounded-full bg-primary/10 text-primary flex items-center justify-center shrink-0">
              <Timer className="h-4 w-4" />
            </div>
            <div>
              <h3 className="text-sm font-semibold flex items-center gap-1.5">
                <span>自动化生产力收益</span>
                <span className="text-xs px-2 py-0.5 rounded-full bg-primary/10 text-primary font-medium flex items-center gap-1">
                  <TrendingUp className="h-3 w-3" />
                  ROI {summary.roi_multiple ?? 0}x
                </span>
              </h3>
              <p className="text-xs text-muted-foreground">基于自动化任务基线工时与实际执行量量化</p>
            </div>
          </div>
          <div className="text-left sm:text-right">
            <div className="text-xs text-muted-foreground">累计节省工时</div>
            <div className="text-xl font-bold tabular-nums text-primary">
              {summary.estimated_hours_saved ?? 0} <span className="text-xs font-normal text-muted-foreground">小时</span>
            </div>
          </div>
        </div>

        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 text-sm pt-1">
          <Metric label={t('statTotalRuns')} value={String(summary.total_runs)} />
          <Metric label={t('statSuccessRate')} value={`${successRate}%`} />
          <Metric
            label={t('statTotalTokens')}
            value={formatTokens(summary.total_tokens)}
            sub={`${t('statInput')} ${formatTokens(summary.total_input_tokens)} / ${t('statOutput')} ${formatTokens(summary.total_output_tokens)}`}
          />
          <Metric
            label="预估生产力价值"
            value={`$${(((summary.estimated_value_saved_cents ?? 0) / 100)).toFixed(1)}`}
            sub={`Token成本 $${(((summary.estimated_cost_cents ?? 0) / 100)).toFixed(2)}`}
          />
        </div>
      </div>

      {by_job.length > 0 && (
        <TableSection title={t('chartByJob')}>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{t('columnJobName')}</TableHead>
                <TableHead className="text-right">{t('columnRuns')}</TableHead>
                <TableHead className="text-right">Tokens</TableHead>
                <TableHead className="text-right">{t('columnPct')}</TableHead>
                <TableHead className="text-right">预估省时</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {by_job.map((row: UsageByJob) => (
                <TableRow key={row.job_id}>
                  <TableCell className="truncate max-w-[200px]">{row.job_name}</TableCell>
                  <TableCell className="text-right tabular-nums text-muted-foreground">{row.runs}</TableCell>
                  <TableCell className="text-right tabular-nums">{formatTokens(row.total_tokens)}</TableCell>
                  <TableCell className="text-right tabular-nums text-muted-foreground">
                    {pct(row.total_tokens, summary.total_tokens)}
                  </TableCell>
                  <TableCell className="text-right tabular-nums text-primary font-medium">
                    {row.hours_saved ?? 0}h
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </TableSection>
      )}

      {by_model.length > 0 && (
        <TableSection title={t('chartByModel')}>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{t('columnModel')}</TableHead>
                <TableHead className="text-right">{t('columnRuns')}</TableHead>
                <TableHead className="text-right">Tokens</TableHead>
                <TableHead className="text-right">{t('columnPct')}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {by_model.map((row: UsageByModel) => (
                <TableRow key={row.model}>
                  <TableCell className="font-mono text-xs">{row.model}</TableCell>
                  <TableCell className="text-right tabular-nums text-muted-foreground">{row.runs}</TableCell>
                  <TableCell className="text-right tabular-nums">{formatTokens(row.total_tokens)}</TableCell>
                  <TableCell className="text-right tabular-nums text-muted-foreground">
                    {pct(row.total_tokens, summary.total_tokens)}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </TableSection>
      )}
    </div>
  );
}

function PeriodSelector({
  period,
  labels,
  onChange,
}: {
  period: Period;
  labels: Record<Period, string>;
  onChange: (p: Period) => void;
}) {
  return (
    <div className="flex gap-1 rounded-lg bg-muted p-1 w-fit">
      {PERIOD_OPTIONS.map((p) => (
        <button
          key={p}
          className={cn(
            'px-3 py-1 text-xs font-medium rounded-full transition-colors',
            period === p ? 'bg-background text-foreground' : 'text-muted-foreground hover:text-foreground',
          )}
          onClick={() => onChange(p)}
        >
          {labels[p]}
        </button>
      ))}
    </div>
  );
}

function Metric({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div>
      <div className="text-xs text-muted-foreground">{label}</div>
      <div className="text-lg font-semibold tabular-nums">{value}</div>
      {sub && <div className="text-xs text-muted-foreground">{sub}</div>}
    </div>
  );
}

function TableSection({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="rounded-lg border bg-card p-4 space-y-2">
      <h3 className="text-sm font-medium">{title}</h3>
      {children}
    </div>
  );
}
