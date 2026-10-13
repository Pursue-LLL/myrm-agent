/** @vitest-environment jsdom */
import { render } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import HealthRadar from '../HealthRadar';

const stableT = (key: string) => key;

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

// What each chart part is handed, so the colours the radar is drawn with can be read back.
const drawn = vi.hoisted(() => ({ props: [] as Array<Record<string, unknown>> }));

vi.mock('@/components/features/app-shell/lazy-recharts', () => {
  const part = (props: Record<string, unknown>) => {
    drawn.props.push(props);
    return null;
  };
  return {
    ResponsiveContainer: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
    RadarChart: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
    PolarGrid: part,
    PolarAngleAxis: part,
    Radar: part,
  };
});

const colorsOf = (props: Record<string, unknown>): string[] =>
  [props.stroke, props.fill, (props.tick as { fill?: string } | undefined)?.fill].filter(
    (value): value is string => typeof value === 'string',
  );

describe('HealthRadar', () => {
  it('colours the radar with theme tokens the browser can read', () => {
    drawn.props.length = 0;

    render(<HealthRadar dimensions={{ freshness: 0.8, coverage: 0.6 }} score={72} />);

    const colors = drawn.props.flatMap(colorsOf);
    // The theme variables hold complete colours (`#6799a0`), which `hsl(var(--x))` turns into an invalid value:
    // no outline, no grid and a black fill.
    expect(colors.length).toBeGreaterThanOrEqual(4);
    for (const color of colors) {
      expect(color).toMatch(/^var\(--[a-z-]+\)$/);
    }
  });
});
