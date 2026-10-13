/**
 * [INPUT]
 * - @/services/statistics::SkillTrendPoint (POS: 技能趋势按日数据点契约)
 *
 * [OUTPUT]
 * - TrendMetric: 趋势图可切换的两个指标（成功率 / 使用次数）
 * - TrendBarDatum: 趋势图一根柱子对应的一个日历日
 * - fillIdleDays: 在技能首末次运行之间补齐没有运行的日子
 * - toBarData: 数据点 -> 柱子数据，0 与无数据分开表达
 * - formatBarValue: 柱子读数文案
 *
 * [POS]
 * 技能趋势图的数据整形，纯函数，可脱离 React 测试。服务端只给有运行的日子，这里把横轴还原成日历。
 */

import type { SkillTrendPoint } from '@/services/statistics';

export type TrendMetric = 'success_rate' | 'call_count';

/** One bar of the trend chart: a calendar day of the viewer. */
export interface TrendBarDatum {
  date: string;
  /** Plotted height; null leaves the day empty instead of drawing a bar. */
  value: number | null;
  /** Runs of the day whose outcome was observed: the evidence behind a success rate. */
  observedCount: number;
  callCount: number;
}

const DAY_MS = 86_400_000;

/**
 * Inserts the days a skill did not run between its first and last run. The server only reports days with runs, and
 * a category axis would otherwise space them evenly: a 9-day pause would look as short as a 1-day one.
 */
export function fillIdleDays(points: SkillTrendPoint[]): SkillTrendPoint[] {
  if (points.length < 2) {
    return points;
  }
  const byDate = new Map(points.map((point) => [point.date, point]));
  const dates = [...byDate.keys()].sort();
  const first = Date.parse(`${dates[0]}T00:00:00Z`);
  const last = Date.parse(`${dates[dates.length - 1]}T00:00:00Z`);
  if (Number.isNaN(first) || Number.isNaN(last)) {
    return points;
  }

  const filled: SkillTrendPoint[] = [];
  for (let day = first; day <= last; day += DAY_MS) {
    const date = new Date(day).toISOString().slice(0, 10);
    filled.push(byDate.get(date) ?? { date, success_rate: null, observed_count: 0, call_count: 0 });
  }
  return filled;
}

export function toBarData(points: SkillTrendPoint[], metric: TrendMetric): TrendBarDatum[] {
  return fillIdleDays(points).map((point) => ({
    date: point.date,
    value: metric === 'success_rate' ? point.success_rate : point.call_count > 0 ? point.call_count : null,
    observedCount: point.observed_count,
    callCount: point.call_count,
  }));
}

export function formatBarValue(metric: TrendMetric, datum: TrendBarDatum): string {
  if (metric === 'call_count') {
    return String(datum.callCount);
  }
  return datum.value === null ? '–' : `${(datum.value * 100).toFixed(0)}%`;
}
