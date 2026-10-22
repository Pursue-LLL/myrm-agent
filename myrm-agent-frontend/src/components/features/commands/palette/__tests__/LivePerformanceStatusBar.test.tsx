/** @vitest-environment jsdom */

import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { LivePerformanceStatusBar } from '../LivePerformanceStatusBar';

const stableT = (key: string) => {
  const table: Record<string, string> = {
    cacheHit: 'Cache 命中',
    ttft: 'TTFT 首字延迟',
    throughput: '实时生成速率',
    estopBtn: '全局急停',
    estopActivated: '全局急停已触发',
  };
  return table[key] ?? key;
};

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

describe('LivePerformanceStatusBar', () => {
  it('renders default telemetry metrics', () => {
    render(<LivePerformanceStatusBar />);

    expect(screen.getByText('Cache 命中:')).toBeInTheDocument();
    expect(screen.getByText('84.5%')).toBeInTheDocument();

    expect(screen.getByText('TTFT 首字延迟:')).toBeInTheDocument();
    expect(screen.getByText('240ms')).toBeInTheDocument();

    expect(screen.getByText('实时生成速率:')).toBeInTheDocument();
    expect(screen.getByText('142.5 tok/s')).toBeInTheDocument();

    expect(screen.getByRole('button', { name: /全局急停/i })).toBeInTheDocument();
  });

  it('renders custom metrics correctly', () => {
    render(
      <LivePerformanceStatusBar
        metrics={{
          cache_hit_rate: 92.1,
          ttft_ms: 180,
          throughput_tokens_per_sec: 210.4,
          estop_active: false,
        }}
      />,
    );

    expect(screen.getByText('92.1%')).toBeInTheDocument();
    expect(screen.getByText('180ms')).toBeInTheDocument();
    expect(screen.getByText('210.4 tok/s')).toBeInTheDocument();
  });

  it('requires two clicks for E-Stop confirmation and calls callback', async () => {
    const handleEStop = vi.fn();
    render(<LivePerformanceStatusBar onTriggerEStop={handleEStop} />);

    const estopButton = screen.getByRole('button', { name: /全局急停/i });
    fireEvent.click(estopButton);

    // Prompt changes to confirmation prompt
    expect(screen.getByText(/Confirm E-Stop\?/i)).toBeInTheDocument();
    expect(handleEStop).not.toHaveBeenCalled();

    // Second click confirms
    fireEvent.click(screen.getByRole('button', { name: /Confirm E-Stop\?/i }));
    expect(handleEStop).toHaveBeenCalledTimes(1);
    expect(screen.getByText('全局急停已触发')).toBeInTheDocument();
  });

  it('renders active E-Stop state if initially activated', () => {
    render(
      <LivePerformanceStatusBar
        metrics={{
          cache_hit_rate: 80.0,
          ttft_ms: 300,
          throughput_tokens_per_sec: 0,
          estop_active: true,
        }}
      />,
    );

    expect(screen.getByText('全局急停已触发')).toBeInTheDocument();
  });
});
