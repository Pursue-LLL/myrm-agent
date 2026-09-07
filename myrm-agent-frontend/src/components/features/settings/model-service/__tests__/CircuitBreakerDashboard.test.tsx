/** @vitest-environment jsdom */
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import React from 'react';
import { CircuitBreakerDashboard } from '../CircuitBreakerDashboard';
import * as llmConfig from '@/services/llm-config';

const stableT = (key: string, params?: Record<string, unknown>) => {
  if (params) {
    let str = key;
    for (const [k, v] of Object.entries(params)) {
      str += `:${k}=${v}`;
    }
    return str;
  }
  return key;
};

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

const mockToast = vi.fn();
vi.mock('@/hooks/shared/useToast', () => ({
  useToast: () => ({ toast: mockToast }),
  toast: (...args: unknown[]) => mockToast(...args),
}));

vi.mock('@/services/llm-config', () => ({
  fetchCircuitBreakersStatus: vi.fn(),
  resetCircuitBreaker: vi.fn(),
}));

describe('CircuitBreakerDashboard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders expand button and healthy indicator initially', () => {
    const { getByTestId } = render(<CircuitBreakerDashboard />);
    expect(getByTestId('toggle-circuit-breaker-dashboard')).toBeInTheDocument();
  });

  it('fetches and displays circuit breaker stats when expanded', async () => {
    vi.mocked(llmConfig.fetchCircuitBreakersStatus).mockResolvedValueOnce({
      'openai:gpt-4o': {
        state: 'closed',
        failure_count: 0,
        half_open_calls: 0,
        retry_after_ms: 0,
      },
      'anthropic:claude-3-7-sonnet': {
        state: 'open',
        failure_count: 5,
        half_open_calls: 0,
        retry_after_ms: 25000,
      },
    });

    render(<CircuitBreakerDashboard />);
    const toggleBtn = screen.getByTestId('toggle-circuit-breaker-dashboard');
    fireEvent.click(toggleBtn);

    await waitFor(() => {
      expect(llmConfig.fetchCircuitBreakersStatus).toHaveBeenCalled();
      expect(screen.getByText('openai:gpt-4o')).toBeInTheDocument();
      expect(screen.getByText('anthropic:claude-3-7-sonnet')).toBeInTheDocument();
      expect(screen.getByText('closed')).toBeInTheDocument();
      expect(screen.getByText('open')).toBeInTheDocument();
    });
  });

  it('triggers reset all circuit breakers', async () => {
    vi.mocked(llmConfig.fetchCircuitBreakersStatus).mockResolvedValue({
      'anthropic:claude-3-7-sonnet': {
        state: 'open',
        failure_count: 5,
        half_open_calls: 0,
        retry_after_ms: 25000,
      },
    });
    vi.mocked(llmConfig.resetCircuitBreaker).mockResolvedValueOnce({
      reset_count: 1,
      success: true,
    });

    render(<CircuitBreakerDashboard />);
    fireEvent.click(screen.getByTestId('toggle-circuit-breaker-dashboard'));

    await waitFor(() => {
      expect(screen.getByTestId('reset-circuit-breakers-btn')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByTestId('reset-circuit-breakers-btn'));

    await waitFor(() => {
      expect(llmConfig.resetCircuitBreaker).toHaveBeenCalledWith(undefined);
      expect(mockToast).toHaveBeenCalledWith(
        expect.objectContaining({
          title: 'resetCircuitBreakerSuccess:count=1',
        }),
      );
    });
  });
});
