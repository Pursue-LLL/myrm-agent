/** @vitest-environment jsdom */
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import SkillTrendChart from '../SkillTrendChart';
import type { SkillTrendPoint, SkillTrendSeries } from '@/services/statistics';
import type { TrendBarDatum } from '../skillTrendSeries';

const TRUNCATED_NOTE = 'Earlier runs in this range are not shown.';

const stableT = (key: string) => (key === 'skillTrends.truncated' ? TRUNCATED_NOTE : key);

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

// jsdom has no layout, so the chart library is replaced by stand-ins that expose what the panel feeds it.
const hovered = vi.hoisted(() => ({ datum: null as TrendBarDatum | null }));

vi.mock('@/components/features/app-shell/lazy-recharts', async () => {
  const { cloneElement } = await import('react');
  return {
    ResponsiveContainer: ({ children, height }: { children: React.ReactNode; height: number | string }) => (
      <div data-testid="chart-container" data-height={String(height)}>
        {children}
      </div>
    ),
    BarChart: ({ data, children }: { data: TrendBarDatum[]; children: React.ReactNode }) => (
      <div data-testid="bar-chart" data-rows={JSON.stringify(data)}>
        {children}
      </div>
    ),
    Bar: () => null,
    Tooltip: ({
      content,
    }: {
      content: React.ReactElement<{ active: boolean; payload: Array<{ payload: TrendBarDatum }> }>;
    }) => (hovered.datum ? cloneElement(content, { active: true, payload: [{ payload: hovered.datum }] }) : null),
    XAxis: () => null,
    YAxis: ({ domain }: { domain: Array<number | string> }) => (
      <i data-testid="y-axis" data-domain={JSON.stringify(domain)} />
    ),
  };
});

const point = (
  date: string,
  success_rate: number | null,
  observed_count: number,
  call_count: number,
): SkillTrendPoint => ({
  date,
  success_rate,
  observed_count,
  call_count,
});

const seriesOf = (skill_name: string, truncated: boolean, data_points: SkillTrendPoint[]): SkillTrendSeries => ({
  skill_name,
  truncated,
  data_points,
});

const series = (skill_name: string, truncated: boolean): SkillTrendSeries =>
  seriesOf(skill_name, truncated, [point('2026-10-12', 1, 3, 3)]);

type ChartRow = TrendBarDatum & { fill: string };

const chartRows = (): ChartRow[] => JSON.parse(screen.getByTestId('bar-chart').getAttribute('data-rows') ?? '[]');

const barFills = () => chartRows().map((row) => row.fill);

describe('SkillTrendChart', () => {
  it('notes that earlier runs may be missing when the skill outgrew the history kept for it', () => {
    render(<SkillTrendChart trends={[series('hourly-job', true), series('occasional', false)]} />);

    expect(screen.getByText(TRUNCATED_NOTE)).toBeInTheDocument();
  });

  it('stays quiet for a skill whose history covers the range, and follows the selected skill', () => {
    render(<SkillTrendChart trends={[series('hourly-job', true), series('occasional', false)]} />);

    fireEvent.click(screen.getByRole('button', { name: 'occasional' }));

    expect(screen.queryByText(TRUNCATED_NOTE)).not.toBeInTheDocument();
  });

  it('says that nothing ran in the range instead of drawing an empty chart', () => {
    render(<SkillTrendChart trends={[]} />);

    expect(screen.getByText('skillTrends.empty')).toBeInTheDocument();
    expect(screen.queryByRole('button')).not.toBeInTheDocument();
    expect(screen.queryByTestId('bar-chart')).not.toBeInTheDocument();
  });

  it('lights the busiest skill when a new range no longer contains the selected one', () => {
    const { rerender } = render(
      <SkillTrendChart trends={[series('hourly-job', false), series('occasional', false)]} />,
    );
    fireEvent.click(screen.getByRole('button', { name: 'occasional' }));
    expect(screen.getByRole('button', { name: 'occasional' })).toHaveAttribute('aria-pressed', 'true');

    rerender(<SkillTrendChart trends={[series('hourly-job', false)]} />);

    expect(screen.getByRole('button', { name: 'hourly-job' })).toHaveAttribute('aria-pressed', 'true');
  });

  it('keeps the chart on a skill that has a pill when the selection falls outside the shown ones', () => {
    const tenSkills = (prefix: string) => Array.from({ length: 10 }, (_, index) => `${prefix}-${index}`);
    const seriesOfNames = (names: string[]) => names.map((name) => series(name, false));
    const { rerender } = render(<SkillTrendChart trends={seriesOfNames(tenSkills('old'))} />);
    fireEvent.click(screen.getByRole('button', { name: 'old-9' }));

    rerender(<SkillTrendChart trends={seriesOfNames([...tenSkills('new'), 'old-9'])} />);

    expect(screen.getAllByRole('button', { pressed: true })).toHaveLength(1);
    expect(screen.getByRole('button', { name: 'new-0' })).toHaveAttribute('aria-pressed', 'true');
  });
});

describe('SkillTrendChart bars', () => {
  const sparse = seriesOf('nightly-report', false, [
    point('2026-10-10', 1, 2, 2),
    point('2026-10-12', 0, 1, 1),
    point('2026-10-13', null, 0, 4),
  ]);

  it('draws the days the skill sat idle as empty slots, so the axis is a calendar', () => {
    render(<SkillTrendChart trends={[sparse]} />);

    expect(chartRows().map((row) => [row.date, row.value])).toEqual([
      ['2026-10-10', 1],
      ['2026-10-11', null],
      ['2026-10-12', 0],
      ['2026-10-13', null],
    ]);
  });

  it('colours only the day that failed throughout as a failure', () => {
    render(<SkillTrendChart trends={[sparse]} />);

    const [ok, idle, failed, unobserved] = barFills();
    expect(failed).toContain('red');
    expect([ok, idle, unobserved].every((fill) => fill !== failed)).toBe(true);
  });

  it('plots the runs per day when the metric is switched, leaving idle days empty', () => {
    render(<SkillTrendChart trends={[sparse]} />);

    fireEvent.click(screen.getByRole('button', { name: 'skillTrends.metric.call_count' }));

    expect(chartRows().map((row) => row.value)).toEqual([2, null, 1, 4]);
    expect(new Set(barFills()).size).toBe(1);
  });

  it('gives the chart a pixel height, because a percentage resolves to 0 inside a parent without one', () => {
    render(<SkillTrendChart trends={[sparse]} />);

    const height = screen.getByTestId('chart-container').getAttribute('data-height');

    expect(Number(height)).toBeGreaterThan(0);
  });

  it('scales the success rate to 0-100% whatever the best day was, and the run count to its own peak', () => {
    render(<SkillTrendChart trends={[sparse]} />);
    const domain = () => JSON.parse(screen.getByTestId('y-axis').getAttribute('data-domain') ?? '[]');

    expect(domain()).toEqual([0, 1]);

    fireEvent.click(screen.getByRole('button', { name: 'skillTrends.metric.call_count' }));

    expect(domain()).toEqual([0, 'dataMax']);
  });

  it('reads out the day under the finger with the runs behind its success rate', () => {
    hovered.datum = { date: '2026-10-12', value: 0, observedCount: 1, callCount: 1 };
    try {
      render(<SkillTrendChart trends={[sparse]} />);

      expect(screen.getByText('2026-10-12')).toBeInTheDocument();
      expect(screen.getByText('0% · skillTrends.observedRuns')).toBeInTheDocument();
    } finally {
      hovered.datum = null;
    }
  });

  it('reads out a day nothing was observed on with a dash and no run count', () => {
    hovered.datum = { date: '2026-10-13', value: null, observedCount: 0, callCount: 4 };
    try {
      render(<SkillTrendChart trends={[sparse]} />);

      expect(screen.getByText('–')).toBeInTheDocument();
      expect(screen.queryByText(/skillTrends.observedRuns/)).not.toBeInTheDocument();
    } finally {
      hovered.datum = null;
    }
  });
});
