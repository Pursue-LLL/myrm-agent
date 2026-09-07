/** @vitest-environment jsdom */
import React from 'react';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import RuntimeCostMeterCard from '../RuntimeCostMeterCard';
import {
  getSearchQuotas,
  getBrowserRuntimeSummary,
  getLLMProviderHealth,
  resetSearchQuota,
  resetLLMProviderCircuit,
  updateSearchQuotaLimit,
} from '@/services/statistics';

const mockT = (key: string, params?: Record<string, unknown>) => {
  if (params?.percent !== undefined) return `Warning (${params.percent}%)`;
  if (params?.count !== undefined) return `Count: ${params.count}`;
  return key;
};

vi.mock('next-intl', () => ({
  useTranslations: () => mockT,
  useLocale: () => 'en',
}));

vi.mock('@/services/statistics', () => ({
  getSearchQuotas: vi.fn(),
  getBrowserRuntimeSummary: vi.fn(),
  getLLMProviderHealth: vi.fn(),
  resetSearchQuota: vi.fn(),
  resetLLMProviderCircuit: vi.fn(),
  updateSearchQuotaLimit: vi.fn(),
}));

describe('RuntimeCostMeterCard', () => {
  const mockQuotas = [
    {
      provider: 'tavily',
      year_month: '2026-09',
      used_count: 850,
      quota_limit: 1000,
      remaining_count: 150,
      percentage: 85.0,
      is_metered: true,
      is_depleted: false,
      status: 'warning' as const,
      last_depleted_at: null,
    },
    {
      provider: 'searxng',
      year_month: '2026-09',
      used_count: 120,
      quota_limit: 100000,
      remaining_count: 99880,
      percentage: 0.1,
      is_metered: false,
      is_depleted: false,
      status: 'healthy' as const,
      last_depleted_at: null,
    },
  ];

  const mockBrowserSummary = {
    year_month: '2026-09',
    session_count: 4,
    total_duration_minutes: 24.5,
    active_compute_minutes: 12.0,
    total_bytes_transferred: 15728640,
    total_megabytes_transferred: 15.0,
    total_requests: 88,
    total_failed_requests: 1,
    estimated_compute_cost_usd: 0.012,
  };

  beforeEach(() => {
    vi.clearAllMocks();
    (getSearchQuotas as unknown as ReturnType<typeof vi.fn>).mockResolvedValue(mockQuotas);
    (getBrowserRuntimeSummary as unknown as ReturnType<typeof vi.fn>).mockResolvedValue(mockBrowserSummary);
    (getLLMProviderHealth as unknown as ReturnType<typeof vi.fn>).mockResolvedValue({
      circuit_breakers: {
        'openai:gpt-4o': {
          state: 'closed',
          failure_count: 0,
          half_open_calls: 0,
          retry_after_ms: 0,
        },
        'deepseek:deepseek-chat': {
          state: 'open',
          failure_count: 5,
          half_open_calls: 0,
          retry_after_ms: 25000,
        },
      },
    });
  });

  it('renders search quotas and browser runtime telemetry cards correctly', async () => {
    render(<RuntimeCostMeterCard />);

    await waitFor(() => {
      expect(screen.getByText('title')).toBeInTheDocument();
    });
    expect(screen.getByText('tavily')).toBeInTheDocument();
    expect(screen.getByText('searxng')).toBeInTheDocument();
    expect(screen.getByText(/\$0\.012/)).toBeInTheDocument();
    expect(screen.getByText('localComputeFree')).toBeInTheDocument();
    expect(screen.getByText('openai:gpt-4o')).toBeInTheDocument();
    expect(screen.getByText('deepseek:deepseek-chat')).toBeInTheDocument();
  });

  it('handles reset circuit breaker action smoothly', async () => {
    (resetLLMProviderCircuit as unknown as ReturnType<typeof vi.fn>).mockResolvedValue({ reset_count: 1 });

    render(<RuntimeCostMeterCard />);

    await waitFor(() => {
      expect(screen.getByText('circuitResetOne')).toBeInTheDocument();
    });

    const resetOneBtn = screen.getByText('circuitResetOne').closest('button');
    expect(resetOneBtn).toBeDefined();
    if (resetOneBtn) {
      fireEvent.click(resetOneBtn);
    }

    await waitFor(() => {
      expect(resetLLMProviderCircuit).toHaveBeenCalledWith('deepseek:deepseek-chat');
    });
  });

  it('handles recalibrate reset action smoothly', async () => {
    (resetSearchQuota as unknown as ReturnType<typeof vi.fn>).mockResolvedValue({ reset_records_count: 2 });

    render(<RuntimeCostMeterCard />);

    await waitFor(() => {
      expect(screen.getByText('resetAll')).toBeInTheDocument();
    });

    const resetButton = screen.getByText('resetAll').closest('button');
    expect(resetButton).toBeDefined();
    if (resetButton) {
      fireEvent.click(resetButton);
    }

    await waitFor(() => {
      expect(resetSearchQuota).toHaveBeenCalledWith(undefined);
    });
  });
});
