import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { RoiValueDashboardCard } from '../RoiValueDashboardCard';
import type { RoiMetricsSnapshot } from '../roiTypes';

const mockTranslations = (key: string, values?: Record<string, unknown>) => {
  if (key === 'hoursEquivalenceHint') {
    return `Calculated at $${values?.rate}/h`;
  }
  if (key === 'tasksCount') {
    return `${values?.count} tasks`;
  }
  if (key === 'digestSummarySnippet') {
    return `Automated ${values?.tasks} tasks, saving ${values?.hours} hours`;
  }
  return key;
};

vi.mock('next-intl', () => ({
  useTranslations: () => mockTranslations,
}));

describe('RoiValueDashboardCard', () => {
  const dummyMetrics: RoiMetricsSnapshot = {
    time_range: 'today',
    total_hours_saved: 14.2,
    total_monetary_saved_usd: 540.0,
    total_compute_cost_usd: 0.35,
    net_roi_multiplier: 1542.8,
    hourly_rate_baseline_usd: 35.0,
    categories_breakdown: [
      {
        category_key: 'code_refactor',
        label_zh: '代码重构与迁移',
        label_en: 'Code Refactor',
        tasks_count: 3,
        hours_saved: 7.5,
        value_usd: 375.0,
      },
      {
        category_key: 'chat_digest',
        label_zh: 'IM 群聊与晨报总结',
        label_en: 'Chat Digest',
        tasks_count: 4,
        hours_saved: 3.2,
        value_usd: 80.0,
      },
    ],
    recent_digest: {
      week_label: 'Week 41 · 2026',
      total_tasks_completed: 28,
      total_hours_saved: 42.5,
      total_value_usd: 1487.5,
      total_token_cost_usd: 1.25,
      net_roi_multiplier: 1190.0,
      top_performer_agent: 'FullStack Engineer (Coder)',
      prevented_errors_count: 9,
    },
  };

  it('renders hero metrics, economic comparison, and category breakdown', () => {
    render(<RoiValueDashboardCard metrics={dummyMetrics} />);

    expect(screen.getByTestId('roi-dashboard-card-root')).toBeInTheDocument();
    expect(screen.getByTestId('hours-saved-billboard')).toBeInTheDocument();
    expect(screen.getByTestId('total-hours-saved-val')).toHaveTextContent('14.2');
    expect(screen.getByTestId('net-roi-badge')).toHaveTextContent('1542.8x ROI');
    expect(screen.getByTestId('monetary-saved-val')).toHaveTextContent('$540');
    expect(screen.getByTestId('compute-cost-val')).toHaveTextContent('$0.35');

    // Category breakdown items
    expect(screen.getByTestId('category-item-code_refactor')).toBeInTheDocument();
    expect(screen.getByTestId('category-item-chat_digest')).toBeInTheDocument();
    expect(screen.getByText('代码重构与迁移')).toBeInTheDocument();
    expect(screen.getByText('7.5h')).toBeInTheDocument();
  });

  it('triggers onTimeRangeChange when switching time range tabs', async () => {
    const onRangeChangeMock = vi.fn();
    render(
      <RoiValueDashboardCard
        metrics={dummyMetrics}
        onTimeRangeChange={onRangeChangeMock}
      />
    );

    const weekBtn = screen.getByTestId('roi-range-btn-week');
    fireEvent.click(weekBtn);

    expect(onRangeChangeMock).toHaveBeenCalledWith('week');
  });

  it('opens weekly digest modal when digest button is clicked', async () => {
    render(<RoiValueDashboardCard metrics={dummyMetrics} />);

    expect(screen.queryByTestId('weekly-digest-modal')).toBeNull();

    const openDigestBtn = screen.getByTestId('open-digest-btn');
    fireEvent.click(openDigestBtn);

    expect(screen.getByTestId('weekly-digest-modal')).toBeInTheDocument();
    expect(screen.getByText('FullStack Engineer (Coder)')).toBeInTheDocument();
    expect(screen.getByText('+9')).toBeInTheDocument();

    // Close modal
    const closeBtn = screen.getByTestId('close-digest-modal-btn');
    fireEvent.click(closeBtn);

    await waitFor(() => {
      expect(screen.queryByTestId('weekly-digest-modal')).toBeNull();
    });
  });

  it('triggers custom onOpenDigest callback if provided', () => {
    const onOpenDigestMock = vi.fn();
    render(
      <RoiValueDashboardCard
        metrics={dummyMetrics}
        onOpenDigest={onOpenDigestMock}
      />
    );

    const openDigestBtn = screen.getByTestId('open-digest-btn');
    fireEvent.click(openDigestBtn);

    expect(onOpenDigestMock).toHaveBeenCalledTimes(1);
    expect(screen.queryByTestId('weekly-digest-modal')).toBeNull();
  });
});
