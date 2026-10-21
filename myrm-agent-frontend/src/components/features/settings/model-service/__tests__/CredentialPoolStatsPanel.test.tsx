/** @vitest-environment jsdom */
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import React from 'react';
import { CredentialPoolStatsPanel } from '../CredentialPoolStatsPanel';
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
  fetchCredentialPoolStats: vi.fn(),
  resetCredentialPoolCooldowns: vi.fn(),
}));

describe('CredentialPoolStatsPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders nothing when hasMultipleKeys is false', () => {
    const { container } = render(<CredentialPoolStatsPanel hasMultipleKeys={false} />);
    expect(container.firstChild).toBeNull();
  });

  it('renders expand button and fetches stats on click', async () => {
    vi.mocked(llmConfig.fetchCredentialPoolStats).mockResolvedValueOnce([
      {
        cache_key: 'openai:gpt-4o',
        model: 'gpt-4o',
        stats: {
          strategy: 'least_used',
          total_keys: 2,
          available_keys: 2,
          total_calls: 15,
          total_rate_limits: 1,
          max_consecutive_rate_limits: 0,
          total_errors: 1,
          keys: [
            {
              suffix: '1234',
              calls: 10,
              rate_limits: 0,
              consecutive_rate_limits: 0,
              errors: 0,
              in_cooldown: false,
              cooldown_remaining_s: 0,
            },
            {
              suffix: '5678',
              calls: 5,
              rate_limits: 1,
              consecutive_rate_limits: 1,
              errors: 1,
              in_cooldown: true,
              cooldown_remaining_s: 30,
            },
          ],
        },
      },
    ]);

    render(<CredentialPoolStatsPanel hasMultipleKeys={true} />);

    const toggleBtn = screen.getByTestId('toggle-pool-stats');
    expect(toggleBtn).toBeDefined();

    fireEvent.click(toggleBtn);

    await waitFor(() => {
      expect(llmConfig.fetchCredentialPoolStats).toHaveBeenCalled();
      expect(screen.getByText('gpt-4o')).toBeDefined();
      expect(screen.getByText('...1234')).toBeDefined();
      expect(screen.getByText('...5678')).toBeDefined();
    });
  });

  it('calls resetCredentialPoolCooldowns and displays toast', async () => {
    vi.mocked(llmConfig.fetchCredentialPoolStats).mockResolvedValue([
      {
        cache_key: 'test-pool',
        model: 'test-model',
        stats: {
          strategy: 'round_robin',
          total_keys: 1,
          available_keys: 1,
          total_calls: 5,
          total_rate_limits: 0,
          max_consecutive_rate_limits: 0,
          total_errors: 0,
          keys: [
            {
              suffix: '9999',
              calls: 5,
              rate_limits: 0,
              consecutive_rate_limits: 0,
              errors: 0,
              in_cooldown: false,
              cooldown_remaining_s: 0,
            },
          ],
        },
      },
    ]);
    vi.mocked(llmConfig.resetCredentialPoolCooldowns).mockResolvedValueOnce({ reset_count: 2 });

    render(<CredentialPoolStatsPanel hasMultipleKeys={true} />);

    // Expand panel first
    fireEvent.click(screen.getByTestId('toggle-pool-stats'));

    await waitFor(() => {
      expect(screen.getByTestId('reset-cooldowns-btn')).toBeDefined();
    });

    fireEvent.click(screen.getByTestId('reset-cooldowns-btn'));

    await waitFor(() => {
      expect(llmConfig.resetCredentialPoolCooldowns).toHaveBeenCalledWith(undefined);
      expect(mockToast).toHaveBeenCalledWith(
        expect.objectContaining({
          title: expect.stringContaining('resetCooldownsSuccess:count=2'),
        }),
      );
    });
  });
});
