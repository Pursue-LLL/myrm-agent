import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import React from 'react';
import CronUsageStats from '../CronUsageStats';
import { fetchUsageStats } from '@/services/cron';
import type { UsageStatsResponse } from '@/services/cron';

const stableT = (key: string) => key;
vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
  useLocale: () => 'zh',
}));

vi.mock('@/services/cron', () => ({
  fetchUsageStats: vi.fn(),
}));

describe('CronUsageStats - Productivity & ROI Visualizer', () => {
  const fetchMock = vi.mocked(fetchUsageStats);

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders empty state when total_runs is 0', async () => {
    const emptyData: UsageStatsResponse = {
      summary: {
        total_runs: 0,
        success_runs: 0,
        total_input_tokens: 0,
        total_output_tokens: 0,
        total_tokens: 0,
        avg_tokens_per_run: 0,
        estimated_hours_saved: 0.0,
        roi_multiple: 0.0,
        estimated_value_saved_cents: 0.0,
        estimated_cost_cents: 0.0,
      },
      by_day: [],
      by_job: [],
      by_model: [],
    };
    fetchMock.mockResolvedValue(emptyData);

    render(<CronUsageStats />);

    await waitFor(() => {
      expect(screen.getByText('noUsageData')).toBeInTheDocument();
    });
  });

  it('renders Productivity ROI card, saved hours, and by_job hours_saved metrics', async () => {
    const populatedData: UsageStatsResponse = {
      summary: {
        total_runs: 24,
        success_runs: 20,
        total_input_tokens: 120000,
        total_output_tokens: 80000,
        total_tokens: 200000,
        avg_tokens_per_run: 8333,
        estimated_hours_saved: 3.3,
        roi_multiple: 250.0,
        estimated_value_saved_cents: 10000.0,
        estimated_cost_cents: 40.0,
      },
      by_day: [
        {
          date: '2026-10-10',
          input_tokens: 120000,
          output_tokens: 80000,
          total_tokens: 200000,
          runs: 24,
        },
      ],
      by_job: [
        {
          job_id: 'job-1',
          job_name: 'Daily Article Digest',
          total_tokens: 120000,
          runs: 12,
          hours_saved: 2.0,
        },
        {
          job_id: 'job-2',
          job_name: 'GitHub PR Monitor',
          total_tokens: 80000,
          runs: 12,
          hours_saved: 1.3,
        },
      ],
      by_model: [
        {
          model: 'gpt-4o',
          total_tokens: 200000,
          runs: 24,
        },
      ],
    };
    fetchMock.mockResolvedValue(populatedData);

    render(<CronUsageStats />);

    await waitFor(() => {
      // 检查自动化生产力收益看板
      expect(screen.getByText('自动化生产力收益')).toBeInTheDocument();
      expect(screen.getByText(/ROI 250x/)).toBeInTheDocument();
      expect(screen.getByText('3.3')).toBeInTheDocument();
      expect(screen.getByText('累计节省工时')).toBeInTheDocument();
      expect(screen.getByText('预估生产力价值')).toBeInTheDocument();
      expect(screen.getByText('$100.0')).toBeInTheDocument();

      // 检查任务列表及预估省时列
      expect(screen.getByText('Daily Article Digest')).toBeInTheDocument();
      expect(screen.getByText('2h')).toBeInTheDocument();
      expect(screen.getByText('GitHub PR Monitor')).toBeInTheDocument();
      expect(screen.getByText('1.3h')).toBeInTheDocument();
    });
  });

  it('triggers period reload when clicking period selector buttons', async () => {
    const baseData: UsageStatsResponse = {
      summary: {
        total_runs: 5,
        success_runs: 5,
        total_input_tokens: 10000,
        total_output_tokens: 5000,
        total_tokens: 15000,
        avg_tokens_per_run: 3000,
        estimated_hours_saved: 0.8,
        roi_multiple: 83.3,
        estimated_value_saved_cents: 2500.0,
        estimated_cost_cents: 3.0,
      },
      by_day: [],
      by_job: [],
      by_model: [],
    };
    fetchMock.mockResolvedValue(baseData);

    render(<CronUsageStats />);

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(7);
    });

    const btn30d = screen.getByText('period30d');
    fireEvent.click(btn30d);

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(30);
    });

    const btnAll = screen.getByText('periodAll');
    fireEvent.click(btnAll);

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(0);
    });
  });
});
