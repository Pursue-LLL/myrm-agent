/** @vitest-environment jsdom */
import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import type { LayerWatermarkResponse } from '@/services/memory/profileNotes';

import { WatermarkBar, levelForRatio } from '../WatermarkBar';

vi.mock('next-intl', async () => (await import('@/test-utils/realIntl')).createRealIntlMock(() => 'en'));

const watermark = (overrides: Partial<LayerWatermarkResponse>): LayerWatermarkResponse => ({
  layer: 'user',
  current_chars: 1200,
  max_chars: 1375,
  usage_ratio: 0.87,
  level: 'warning',
  warning_message: null,
  ...overrides,
});

describe('levelForRatio', () => {
  it.each([
    [0, 'safe'],
    [0.69, 'safe'],
    [0.7, 'warning'],
    [0.89, 'warning'],
    [0.9, 'critical'],
    [1, 'critical'],
    [1.01, 'overflow'],
  ] as const)('maps %s to %s', (ratio, level) => {
    expect(levelForRatio(ratio)).toBe(level);
  });
});

describe('WatermarkBar', () => {
  it('shows the capacity sentence, the level badge and the server warning', () => {
    render(<WatermarkBar watermark={watermark({ warning_message: 'Close to the limit' })} />);

    expect(screen.getByText('Capacity: 1,200 / 1,375 characters (87%)')).toBeInTheDocument();
    expect(screen.getByText('Warning')).toBeInTheDocument();
    expect(screen.getByText('Close to the limit')).toBeInTheDocument();
  });

  it('caps the bar at 100 percent and labels the overflow', () => {
    render(<WatermarkBar watermark={watermark({ usage_ratio: 1.4, level: 'overflow', current_chars: 1925 })} />);

    expect(screen.getByText('Capacity: 1,925 / 1,375 characters (100%)')).toBeInTheDocument();
    expect(screen.getByText('Over limit')).toBeInTheDocument();
  });
});
