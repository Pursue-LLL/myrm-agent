import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import TurnGrowthSparkline from '../TurnGrowthSparkline';
import type { ContextWatermarkMetrics } from '../useContextWatermarkMetrics';

const translate = vi.hoisted(() => (key: string, params?: Record<string, unknown>) => {
  if (params) {
    return `${key}:${JSON.stringify(params)}`;
  }
  return key;
});

vi.mock('next-intl', () => ({
  useTranslations: () => translate,
}));

function createMockMetrics(overrides?: Partial<ContextWatermarkMetrics>): ContextWatermarkMetrics {
  return {
    latestBudget: {
      current_tokens: 5000,
      max_context_tokens: 128000,
      usage_percent: 30,
      health_status: 'healthy',
    },
    historyTurnTokens: [3000, 5000],
    deltaTokens: 2000,
    hasDelta: true,
    usagePercent: 30,
    weatherTier: 'cloudy',
    weatherBadgeClass: 'bg-sky-500/10 text-sky-600',
    weatherLabelKey: 'weatherCloudy',
    ...overrides,
  };
}

describe('TurnGrowthSparkline', () => {
  it('returns null when historyTurnTokens is empty', () => {
    const { container } = render(
      <TurnGrowthSparkline metrics={createMockMetrics({ historyTurnTokens: [] })} />,
    );
    expect(container.firstChild).toBeNull();
  });

  it('renders SVG sparkline, weather badge and positive delta', () => {
    render(<TurnGrowthSparkline metrics={createMockMetrics()} />);

    expect(screen.getByTestId('turn-growth-sparkline')).toBeDefined();
    expect(screen.getByTestId('sparkline-weather-badge').textContent).toBe('weatherCloudy');

    const deltaBadge = screen.getByTestId('sparkline-delta-badge');
    expect(deltaBadge.textContent).toContain('deltaPositive:{"tokens":"2K"}');
  });

  it('renders negative delta after compaction', () => {
    const metrics = createMockMetrics({
      historyTurnTokens: [80000, 20000],
      deltaTokens: -60000,
      hasDelta: true,
      weatherTier: 'clear',
      weatherLabelKey: 'weatherClear',
    });
    render(<TurnGrowthSparkline metrics={metrics} />);

    const deltaBadge = screen.getByTestId('sparkline-delta-badge');
    expect(deltaBadge.textContent).toContain('deltaNegative:{"tokens":"60K"}');
  });

  it('renders deltaZero when delta is 0', () => {
    const metrics = createMockMetrics({
      historyTurnTokens: [5000, 5000],
      deltaTokens: 0,
      hasDelta: true,
    });
    render(<TurnGrowthSparkline metrics={metrics} />);

    const deltaBadge = screen.getByTestId('sparkline-delta-badge');
    expect(deltaBadge.textContent).toBe('deltaZero');
  });

  it('does not render delta badge when hasDelta is false (single turn)', () => {
    const metrics = createMockMetrics({
      historyTurnTokens: [5000],
      deltaTokens: 0,
      hasDelta: false,
    });
    render(<TurnGrowthSparkline metrics={metrics} />);

    expect(screen.queryByTestId('sparkline-delta-badge')).toBeNull();
  });

  it('shows tooltip on point hover', () => {
    const { container } = render(
      <TurnGrowthSparkline metrics={createMockMetrics({ historyTurnTokens: [3000, 5000] })} />,
    );

    const circles = container.querySelectorAll('circle');
    expect(circles.length).toBe(2);

    fireEvent.mouseEnter(circles[0]);
    expect(screen.getByTestId('sparkline-tooltip').textContent).toBe('3K');

    fireEvent.mouseLeave(circles[0]);
    expect(screen.queryByTestId('sparkline-tooltip')).toBeNull();
  });
});
