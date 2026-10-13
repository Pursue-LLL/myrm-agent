'use client';

/**
 * [INPUT]
 * - @/components/features/app-shell/lazy-recharts::Bar, BarChart, ResponsiveContainer, Tooltip, XAxis, YAxis (POS: Recharts 懒加载统一入口)
 * - ./skillTrendSeries::toBarData, formatBarValue (POS: 趋势图数据整形，纯函数)
 * - @/services/statistics::SkillTrendSeries (POS: 技能趋势序列契约)
 *
 * [OUTPUT]
 * - SkillTrendChart: 技能使用趋势图，技能选择、成功率 / 次数切换、日粒度柱状图与账本截断说明
 *
 * [POS]
 * 成长看板的技能趋势面板。柱区定高，悬停与触摸读出当日值；窗口随看板所选时间范围。
 */

import { memo, useMemo, useState } from 'react';
import { useTranslations } from 'next-intl';
import { TrendingUp, CheckCircle2 } from 'lucide-react';
import {
  Bar,
  BarChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from '@/components/features/app-shell/lazy-recharts';
import { cn } from '@/lib/utils/classnameUtils';
import type { SkillTrendSeries } from '@/services/statistics';
import { formatBarValue, toBarData, type TrendBarDatum, type TrendMetric } from './skillTrendSeries';

/** The busiest skills get a selector pill; the chart always shows one of them. */
const MAX_SKILL_PILLS = 10;

/** A fixed pixel height: the chart's own height cannot depend on a parent that has none. */
const CHART_HEIGHT = 128;

/** Above this many bars they sit a pixel apart, so a 90-day range still fits a phone. */
const DENSE_BAR_COUNT = 45;

// Opaque 600 shades keep every bar at 3:1 or better against the card of both themes; the theme's own
// `--destructive` is a dark red in the dark theme (2:1) and would nearly vanish there.
const FAILURE_COLOR = 'var(--color-red-600, #dc2626)';

const METRIC_CONFIG: Record<TrendMetric, { icon: typeof TrendingUp; barColor: string }> = {
  success_rate: { icon: CheckCircle2, barColor: 'var(--color-emerald-600, #059669)' },
  call_count: { icon: TrendingUp, barColor: 'var(--color-blue-600, #2563eb)' },
};

interface TrendTooltipProps {
  metric: TrendMetric;
  active?: boolean;
  payload?: ReadonlyArray<{ payload: TrendBarDatum }>;
}

/** Cloned by the chart with the hovered or touched day; shows the day's value and the runs behind a success rate. */
function SkillTrendTooltip({ metric, active, payload }: TrendTooltipProps) {
  const t = useTranslations('growthDashboard');
  const datum = payload?.[0]?.payload;
  if (!active || !datum) {
    return null;
  }
  return (
    <div className="rounded-lg border border-border bg-popover px-2.5 py-1.5 text-xs text-popover-foreground shadow-md">
      <p className="font-medium">{datum.date}</p>
      <p className="text-muted-foreground">
        {formatBarValue(metric, datum)}
        {metric === 'success_rate' &&
          datum.value !== null &&
          ` · ${t('skillTrends.observedRuns', { count: datum.observedCount })}`}
      </p>
    </div>
  );
}

const SkillTrendChart = memo<{ trends: SkillTrendSeries[] }>(({ trends }) => {
  const t = useTranslations('growthDashboard');
  const [selectedSkill, setSelectedSkill] = useState<string | null>(null);
  const [metric, setMetric] = useState<TrendMetric>('success_rate');

  const pills = useMemo(() => trends.slice(0, MAX_SKILL_PILLS), [trends]);
  // A selection the range no longer contains falls back to the busiest skill, so a pill is always lit.
  const activeTrend = useMemo(
    () => pills.find((s) => s.skill_name === selectedSkill) ?? pills[0],
    [pills, selectedSkill],
  );
  // The colour travels with each row: the lazy chart parts are wrappers, which the library's child-type lookup
  // (`Cell`) does not recognise.
  const bars = useMemo(
    () =>
      toBarData(activeTrend?.data_points ?? [], metric).map((bar) => ({
        ...bar,
        fill: bar.value === 0 ? FAILURE_COLOR : METRIC_CONFIG[metric].barColor,
      })),
    [activeTrend, metric],
  );

  if (trends.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-12 text-center">
        <TrendingUp className="h-10 w-10 text-muted-foreground/30 mb-3" />
        <p className="text-sm text-muted-foreground">{t('skillTrends.empty')}</p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Skill selector */}
      <div className="flex flex-wrap gap-1.5">
        {pills.map((s) => {
          const isActive = activeTrend?.skill_name === s.skill_name;
          return (
            <button
              key={s.skill_name}
              type="button"
              onClick={() => setSelectedSkill(s.skill_name)}
              aria-pressed={isActive}
              className={cn(
                'px-2.5 py-1 text-xs rounded-full border transition-colors',
                isActive
                  ? 'bg-primary/10 border-primary/30 text-primary font-medium'
                  : 'border-border/60 text-muted-foreground hover:border-border',
              )}
            >
              {s.skill_name}
            </button>
          );
        })}
      </div>

      {/* Metric toggle */}
      <div className="flex gap-1 rounded-lg border bg-muted/50 p-0.5 w-fit">
        {(Object.keys(METRIC_CONFIG) as TrendMetric[]).map((key) => {
          const cfg = METRIC_CONFIG[key];
          const Icon = cfg.icon;
          return (
            <button
              key={key}
              type="button"
              onClick={() => setMetric(key)}
              className={cn(
                'flex items-center gap-1.5 px-2.5 py-1 text-xs font-medium rounded-md transition-colors',
                metric === key
                  ? 'bg-background text-foreground shadow-sm'
                  : 'text-muted-foreground hover:text-foreground',
              )}
            >
              <Icon className="h-3 w-3" />
              {t(`skillTrends.metric.${key}`)}
            </button>
          );
        })}
      </div>

      {/* Chart bars: an empty slot is a day nothing was observed, a short red bar a day that failed throughout */}
      <div className="w-full" style={{ height: CHART_HEIGHT }}>
        <ResponsiveContainer width="100%" height={CHART_HEIGHT}>
          <BarChart
            data={bars}
            margin={{ top: 4, right: 0, bottom: 0, left: 0 }}
            barCategoryGap={bars.length > DENSE_BAR_COUNT ? 1 : '20%'}
          >
            <XAxis
              dataKey="date"
              tickFormatter={formatDayTick}
              interval="preserveStartEnd"
              minTickGap={28}
              tickLine={false}
              axisLine={false}
              tick={{ fontSize: 10, fill: 'var(--muted-foreground)' }}
            />
            {/* Fixed scale, so a skill that tops out at 50% does not look as good as one at 100% */}
            <YAxis hide domain={metric === 'success_rate' ? [0, 1] : [0, 'dataMax']} />
            <Tooltip
              content={<SkillTrendTooltip metric={metric} />}
              cursor={{ fill: 'var(--muted)', fillOpacity: 0.4 }}
              filterNull={false}
            />
            <Bar dataKey="value" minPointSize={3} maxBarSize={28} radius={[2, 2, 0, 0]} isAnimationActive={false} />
          </BarChart>
        </ResponsiveContainer>
      </div>

      {activeTrend?.truncated && (
        <p className="text-xs leading-relaxed text-muted-foreground">{t('skillTrends.truncated')}</p>
      )}
    </div>
  );
});

SkillTrendChart.displayName = 'SkillTrendChart';

/** `2026-10-12` -> `10-12`: within the 7 to 90 days a chart covers, month and day alone name a day. */
function formatDayTick(date: string): string {
  return date.slice(5);
}

export default SkillTrendChart;
