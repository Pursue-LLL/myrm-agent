'use client';

/**
 * [INPUT] @/services/memory/commandCenter::MemoryCommandDiagnosticHistoryItem (POS: 诊断历史), ./memoryDoctorModel (POS: 格式化函数)
 * [OUTPUT] DiagnosticTrendSection: 最近几次诊断的 recall / ndcg / mrr / 延迟趋势与较上次的变化；CategoryBreakdown: 按类别的通过率
 * [POS] Memory Doctor 面板的历史趋势区。
 */

import type { MemoryCommandDiagnosticHistoryItem } from '@/services/memory/commandCenter';
import { type MemoryTranslation, formatDuration, formatPercent, formatTime } from './memoryDoctorModel';
import { StatusPill } from './MemoryDoctorStatusPill';

const TREND_METRICS = [
  { key: 'recall_at_k', kind: 'percent' },
  { key: 'ndcg_at_k', kind: 'percent' },
  { key: 'mrr_score', kind: 'percent' },
  { key: 'latency_p50_ms', kind: 'ms' },
  { key: 'latency_p95_ms', kind: 'ms' },
  { key: 'latency_p99_ms', kind: 'ms' },
] as const;

type TrendMetricKind = (typeof TREND_METRICS)[number]['kind'];
type TrendMetricKey = (typeof TREND_METRICS)[number]['key'];

export const DiagnosticTrendSection = ({
  history,
  t,
}: {
  history: MemoryCommandDiagnosticHistoryItem[];
  t: MemoryTranslation;
}) => {
  const withBenchmark = history.filter((item) => item.benchmark);
  if (withBenchmark.length < 2) {
    return null;
  }

  const points = [...withBenchmark].reverse();
  const latest = points[points.length - 1];
  const previous = points[points.length - 2];
  if (!latest.benchmark || !previous.benchmark) {
    return null;
  }

  return (
    <div className="rounded-lg border border-border/50 bg-background/70 p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="text-xs font-medium text-foreground">{t('commandCenter.doctorTrendTitle')}</span>
        <div className="flex flex-wrap items-center gap-2">
          {latest.status !== 'ready' && <StatusPill status={latest.status} t={t} />}
          <span className="text-[10px] text-muted-foreground">
            {t('commandCenter.doctorTrendRuns', { count: points.length })}
          </span>
        </div>
      </div>
      <div className="mt-3 grid gap-3 sm:grid-cols-3">
        {TREND_METRICS.map((metric) => (
          <TrendMetric
            key={metric.key}
            metric={metric.key}
            kind={metric.kind}
            points={points}
            latest={latest}
            previous={previous}
            t={t}
          />
        ))}
      </div>
      {latest.embedding_model && previous.embedding_model && latest.embedding_model !== previous.embedding_model && (
        <div className="mt-2 rounded-full border border-amber-500/20 bg-amber-500/10 px-2 py-1 text-[10px] text-amber-700 dark:text-amber-300">
          {t('commandCenter.doctorTrendModelShift', { model: latest.embedding_model })}
        </div>
      )}
      {latest.benchmark && Object.keys(latest.benchmark.categories).length > 0 && (
        <CategoryBreakdown categories={latest.benchmark.categories} t={t} />
      )}
    </div>
  );
};

export const CategoryBreakdown = ({
  categories,
  t,
  bordered = true,
}: {
  categories: Record<string, string>;
  t: MemoryTranslation;
  bordered?: boolean;
}) => {
  const entries = Object.entries(categories);
  if (!entries.length) {
    return null;
  }
  return (
    <div className={bordered ? 'mt-2 border-t border-border/40 pt-2' : ''}>
      <div className="mb-1 text-[10px] text-muted-foreground">{t('commandCenter.benchmarkCategories')}</div>
      <div className="flex flex-wrap gap-1">
        {entries.map(([cat, ratio]) => {
          const [passed, total] = ratio.split('/').map(Number);
          const allPassed = passed === total;
          return (
            <span
              key={cat}
              className={`inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-medium ${
                allPassed
                  ? 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400'
                  : 'bg-amber-500/10 text-amber-600 dark:text-amber-400'
              }`}
            >
              {cat.replace(/_/g, ' ')} {ratio}
            </span>
          );
        })}
      </div>
    </div>
  );
};

const TrendMetric = ({
  metric,
  kind,
  points,
  latest,
  previous,
  t,
}: {
  metric: TrendMetricKey;
  kind: TrendMetricKind;
  points: MemoryCommandDiagnosticHistoryItem[];
  latest: MemoryCommandDiagnosticHistoryItem;
  previous: MemoryCommandDiagnosticHistoryItem;
  t: MemoryTranslation;
}) => {
  const latestSummary = latest.benchmark;
  const previousSummary = previous.benchmark;
  if (!latestSummary || !previousSummary) {
    return null;
  }

  const latestValue = latestSummary[metric];
  const previousValue = previousSummary[metric];
  const delta = latestValue - previousValue;
  const k = latestSummary.top_k;
  const label =
    metric === 'recall_at_k'
      ? t('commandCenter.benchmarkRecall', { k })
      : metric === 'ndcg_at_k'
        ? t('commandCenter.benchmarkNdcg', { k })
        : metric === 'mrr_score'
          ? t('commandCenter.benchmarkMrr')
          : metric === 'latency_p50_ms'
            ? t('commandCenter.benchmarkLatencyP50')
            : metric === 'latency_p95_ms'
              ? t('commandCenter.benchmarkLatencyP95')
              : t('commandCenter.benchmarkLatencyP99');

  const isMs = kind === 'ms';
  const improved = isMs ? delta <= 0 : delta >= 0;
  const pointsToRender = points.slice(-8);
  const maxBar = isMs ? Math.max(...pointsToRender.map((item) => item.benchmark?.[metric] ?? 0), 1) : 1;

  return (
    <div className="rounded-full border border-border/40 bg-muted/30 px-3 py-2">
      <div className="flex items-center justify-between gap-2">
        <span className="text-[10px] text-muted-foreground">{label}</span>
        <span className={improved ? 'text-emerald-500' : 'text-red-500'}>
          {delta > 0 ? '+' : ''}
          {isMs ? formatDuration(delta) : formatPercent(delta)}
        </span>
      </div>
      <div className="mt-1 flex h-10 items-end gap-1">
        {pointsToRender.map((item, index) => (
          <MiniTrendBar
            key={`${item.run_id}-${index}`}
            value={(item.benchmark?.[metric] ?? 0) / maxBar}
            latest={index === pointsToRender.length - 1}
            title={isMs ? formatDuration(item.benchmark?.[metric]) : formatPercent(item.benchmark?.[metric] ?? 0)}
          />
        ))}
      </div>
      <div className="mt-1 flex items-center justify-between">
        <span className="text-xs font-semibold text-foreground">
          {isMs ? formatDuration(latestValue) : formatPercent(latestValue)}
        </span>
        <span className="text-[10px] text-muted-foreground">{formatTime(latest.occurred_at)}</span>
      </div>
    </div>
  );
};

const MiniTrendBar = ({ value, latest, title }: { value: number; latest: boolean; title: string }) => (
  <div
    className={`flex-1 rounded-t-sm ${latest ? 'bg-primary' : 'bg-primary/40'}`}
    style={{ height: `${Math.max(value * 100, 3)}%`, minHeight: 3 }}
    title={title}
  />
);
