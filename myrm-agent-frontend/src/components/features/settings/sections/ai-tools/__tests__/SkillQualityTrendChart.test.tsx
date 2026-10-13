/** @vitest-environment jsdom */
import { render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { SkillQualityTrendChart } from '../SkillQualityTrendChart';

const stableT = (key: string) => key;
const intl = vi.hoisted(() => ({ locale: 'en' }));

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
  useLocale: () => intl.locale,
}));

const api = vi.hoisted(() => ({ apiRequest: vi.fn() }));
vi.mock('@/lib/api', () => ({ apiRequest: api.apiRequest }));

const toastApi = vi.hoisted(() => ({ toast: vi.fn() }));
vi.mock('@/hooks/shared/useToast', () => ({ useToast: () => toastApi }));

// jsdom has no layout, so the chart library is replaced by stand-ins that expose what the panel feeds it.
vi.mock('@/components/features/app-shell/lazy-recharts', () => ({
  ResponsiveContainer: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  LineChart: ({ data, children }: { data: Array<{ date: string }>; children: React.ReactNode }) => (
    <div data-testid="line-chart" data-dates={JSON.stringify(data.map((row) => row.date))}>
      {children}
    </div>
  ),
  Line: ({ dataKey, name }: { dataKey: string; name: string }) => <i data-testid={`line-${dataKey}`}>{name}</i>,
  ReferenceLine: ({ x }: { x: string }) => <i data-testid="evolution-marker" data-x={x} />,
  CartesianGrid: () => null,
  XAxis: () => null,
  YAxis: () => null,
  Tooltip: () => null,
  Legend: () => null,
}));

const TIMESTAMP = '2026-10-12T12:00:00Z';

const trends = (skillId?: string) => ({
  skill_id: skillId,
  data_points: [
    {
      timestamp: TIMESTAMP,
      avg_quality_score: 0.8,
      avg_success_rate: 0.9,
      avg_token_efficiency: 0.7,
      execution_count: 3,
    },
  ],
  evolution_events: [{ date: TIMESTAMP }],
  time_range_days: 30,
});

const chartDates = (): string[] => JSON.parse(screen.getByTestId('line-chart').getAttribute('data-dates') ?? '[]');

const renderChart = async (skillId?: string) => {
  api.apiRequest.mockResolvedValue(trends(skillId));
  render(<SkillQualityTrendChart skillId={skillId} />);
  await waitFor(() => expect(screen.getByTestId('line-chart')).toBeTruthy());
};

describe('SkillQualityTrendChart', () => {
  beforeEach(() => {
    intl.locale = 'en';
    api.apiRequest.mockReset();
  });

  it('formats the day labels in the active locale', async () => {
    await renderChart();
    expect(chartDates()).toEqual(['Oct 12']);
  });

  it('formats the day labels in Chinese when the interface is Chinese', async () => {
    intl.locale = 'zh';
    await renderChart();
    expect(chartDates()).toEqual(['10月12日']);
  });

  it('places the evolution marker on the same label as its data point', async () => {
    await renderChart();
    expect(screen.getByTestId('evolution-marker').getAttribute('data-x')).toBe(chartDates()[0]);
  });

  it('labels the lines and the card title with translation keys only', async () => {
    await renderChart();
    expect(screen.getByText('globalTrend')).toBeTruthy();
    expect(screen.getByTestId('line-Quality Score').textContent).toBe('qualityScore');
    expect(screen.getByTestId('line-Success Rate').textContent).toBe('successRate');
    expect(screen.queryByTestId('line-Token Efficiency')).toBeNull();
  });

  it('adds the token-efficiency line for a single skill', async () => {
    await renderChart('skill-1');
    expect(screen.getByTestId('line-Token Efficiency').textContent).toBe('tokenEfficiency');
  });
});
