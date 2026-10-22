import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, act } from '@testing-library/react';
import { MetricCardinalityCapHUD } from '../MetricCardinalityCapHUD';
import { MetricCardinalityStatItem } from '../metricCardinalityTypes';

describe('MetricCardinalityCapHUD Component', () => {
  const mockStats: MetricCardinalityStatItem[] = [
    {
      metric_name: 'http_inbound_requests_total',
      cap_limit: 128,
      tracked_cardinality: 32,
      overflow_count: 0,
      total_samples: 1420,
      utilization_pct: 25.0,
      status: 'healthy',
      top_tracked_labels: [
        '/api/v1/sessions',
        '/api/v1/chat/completions',
        '/api/v1/tools/execute',
      ],
      label_hits: {
        '/api/v1/sessions': 520,
        '/api/v1/chat/completions': 680,
        '/api/v1/tools/execute': 220,
      },
    },
    {
      metric_name: 'model_fallback_events_total',
      cap_limit: 10,
      tracked_cardinality: 10,
      overflow_count: 4,
      total_samples: 85,
      utilization_pct: 100.0,
      status: 'overflowing',
      top_tracked_labels: ['_overflow_', 'from_gpt4_to_claude', 'from_claude_to_deepseek'],
      label_hits: {
        _overflow_: 4,
        from_gpt4_to_claude: 45,
        from_claude_to_deepseek: 36,
      },
    },
  ];

  it('renders correctly with KPI totals, metric list, and health indicators', () => {
    render(<MetricCardinalityCapHUD stats={mockStats} />);

    expect(screen.getByTestId('metric-cardinality-cap-hud')).toBeInTheDocument();
    expect(screen.getByText('2 个')).toBeInTheDocument();
    expect(screen.getByText('1,505 次')).toBeInTheDocument();
    expect(screen.getAllByText('http_inbound_requests_total').length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText('model_fallback_events_total').length).toBeGreaterThanOrEqual(1);
  });

  it('switches active metric and displays top tracked labels', async () => {
    render(<MetricCardinalityCapHUD stats={mockStats} />);

    // Click the second metric card (model_fallback_events_total)
    const card2 = screen.getByTestId('metric-card-model_fallback_events_total');
    await act(async () => {
      fireEvent.click(card2);
    });

    expect(screen.getByText(/溢出哨兵桶/)).toBeInTheDocument();
    expect(screen.getByText(/from_gpt4_to_claude/)).toBeInTheDocument();
    expect(screen.getByText(/from_claude_to_deepseek/)).toBeInTheDocument();
  });

  it('handles cap configuration update and callbacks', async () => {
    const handleConfigureCap = vi.fn().mockResolvedValue(undefined);
    const handleRefresh = vi.fn();
    const handleReset = vi.fn().mockResolvedValue(undefined);

    render(
      <MetricCardinalityCapHUD
        stats={mockStats}
        onConfigureCap={handleConfigureCap}
        onRefresh={handleRefresh}
        onReset={handleReset}
      />
    );

    // Modify cap input for active metric
    const inputCap = screen.getByTestId('input-cap-http_inbound_requests_total');
    await act(async () => {
      fireEvent.change(inputCap, { target: { value: '256' } });
    });

    const saveBtn = screen.getByTestId('btn-save-cap-http_inbound_requests_total');
    await act(async () => {
      fireEvent.click(saveBtn);
    });

    expect(handleConfigureCap).toHaveBeenCalledWith('http_inbound_requests_total', 256);

    // Click Refresh & Reset
    const refreshBtn = screen.getByTestId('btn-refresh-stats');
    await act(async () => {
      fireEvent.click(refreshBtn);
    });
    expect(handleRefresh).toHaveBeenCalled();

    const resetBtn = screen.getByTestId('btn-reset-governor');
    await act(async () => {
      fireEvent.click(resetBtn);
    });
    expect(handleReset).toHaveBeenCalled();
  });
});
