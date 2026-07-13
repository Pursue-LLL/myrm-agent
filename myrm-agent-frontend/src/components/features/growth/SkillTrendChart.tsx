'use client';

import { memo, useMemo, useState } from 'react';
import { useTranslations } from 'next-intl';
import { TrendingUp, Clock, CheckCircle2 } from 'lucide-react';
import { cn } from '@/lib/utils/classnameUtils';
import type { SkillTrendSeries } from '@/services/statistics';

type MetricKey = 'success_rate' | 'avg_duration_ms' | 'call_count';

const METRIC_CONFIG: Record<MetricKey, { icon: typeof TrendingUp; colorClass: string; barColor: string }> = {
  success_rate: { icon: CheckCircle2, colorClass: 'text-emerald-500', barColor: 'var(--color-emerald-500, #10b981)' },
  avg_duration_ms: { icon: Clock, colorClass: 'text-amber-500', barColor: 'var(--color-amber-500, #f59e0b)' },
  call_count: { icon: TrendingUp, colorClass: 'text-blue-500', barColor: 'var(--color-blue-500, #3b82f6)' },
};

const SkillTrendChart = memo<{ trends: SkillTrendSeries[] }>(({ trends }) => {
  const t = useTranslations('growthDashboard');
  const [selectedSkill, setSelectedSkill] = useState<string | null>(null);
  const [metric, setMetric] = useState<MetricKey>('success_rate');

  const activeTrend = useMemo(
    () => trends.find((s) => s.skill_name === selectedSkill) ?? trends[0],
    [trends, selectedSkill],
  );

  if (trends.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-12 text-center">
        <TrendingUp className="h-10 w-10 text-muted-foreground/30 mb-3" />
        <p className="text-sm text-muted-foreground">{t('skillTrends.empty')}</p>
      </div>
    );
  }

  const dataPoints = activeTrend?.data_points ?? [];
  const maxVal = Math.max(...dataPoints.map((p) => p[metric]), 1);

  return (
    <div className="space-y-4">
      {/* Skill selector */}
      <div className="flex flex-wrap gap-1.5">
        {trends.slice(0, 10).map((s) => (
          <button
            key={s.skill_name}
            type="button"
            onClick={() => setSelectedSkill(s.skill_name)}
            className={cn(
              'px-2.5 py-1 text-xs rounded-full border transition-colors',
              (selectedSkill ?? trends[0]?.skill_name) === s.skill_name
                ? 'bg-primary/10 border-primary/30 text-primary font-medium'
                : 'border-border/60 text-muted-foreground hover:border-border',
            )}
          >
            {s.skill_name}
          </button>
        ))}
      </div>

      {/* Metric toggle */}
      <div className="flex gap-1 rounded-lg border bg-muted/50 p-0.5 w-fit">
        {(Object.keys(METRIC_CONFIG) as MetricKey[]).map((key) => {
          const cfg = METRIC_CONFIG[key];
          const Icon = cfg.icon;
          return (
            <button
              key={key}
              type="button"
              onClick={() => setMetric(key)}
              className={cn(
                'flex items-center gap-1.5 px-2.5 py-1 text-xs font-medium rounded-md transition-colors',
                metric === key ? 'bg-background text-foreground shadow-sm' : 'text-muted-foreground hover:text-foreground',
              )}
            >
              <Icon className="h-3 w-3" />
              {t(`skillTrends.metric.${key}`)}
            </button>
          );
        })}
      </div>

      {/* Chart bars */}
      <div className="flex items-end gap-1 h-32">
        {dataPoints.map((point) => {
          const val = point[metric];
          const height = maxVal > 0 ? (val / maxVal) * 100 : 0;
          const barColor = METRIC_CONFIG[metric].barColor;
          const label = formatMetricValue(metric, val);

          return (
            <div
              key={point.date}
              className="flex-1 flex flex-col items-center gap-1 group"
              title={`${point.date}: ${label}`}
            >
              <span className="text-[10px] text-muted-foreground opacity-0 group-hover:opacity-100 transition-opacity">
                {label}
              </span>
              <div
                className="w-full rounded-t-sm transition-all"
                style={{
                  height: `${Math.max(height, 2)}%`,
                  backgroundColor: barColor,
                  opacity: 0.8,
                }}
              />
              <span className="text-[9px] text-muted-foreground/70 truncate max-w-full">
                {point.date.slice(5)}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
});

SkillTrendChart.displayName = 'SkillTrendChart';

function formatMetricValue(metric: MetricKey, value: number): string {
  switch (metric) {
    case 'success_rate':
      return `${(value * 100).toFixed(0)}%`;
    case 'avg_duration_ms':
      return value >= 1000 ? `${(value / 1000).toFixed(1)}s` : `${value.toFixed(0)}ms`;
    case 'call_count':
      return String(value);
  }
}

export default SkillTrendChart;
