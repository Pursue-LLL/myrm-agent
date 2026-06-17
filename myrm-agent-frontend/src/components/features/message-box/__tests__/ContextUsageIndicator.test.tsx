import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import ContextUsageIndicator from '../ContextUsageIndicator';
import type { ContextHealth } from '@/services/contextHealth';
import type { ContextHealthStatus } from '@/store/chat/types';

const translate = vi.hoisted(() => (key: string, params?: Record<string, unknown>) => {
  if (params) return `${key}:${JSON.stringify(params)}`;
  return key;
});
const mockGetSessionAnalytics = vi.hoisted(() => vi.fn());
const mockCompactChat = vi.hoisted(() => vi.fn());

vi.mock('next-intl', () => ({
  useTranslations: () => translate,
}));

vi.mock('@/services/statistics', () => ({
  getSessionAnalytics: mockGetSessionAnalytics,
}));

vi.mock('@/services/chat', () => ({
  compactChat: mockCompactChat,
}));

vi.mock('@/hooks/useMediaQuery', () => ({
  useIsMobile: () => false,
}));

const mockConfigState = vi.hoisted(() => ({
  showContextUsage: true,
}));

vi.mock('@/store/useConfigStore', () => ({
  default: (selector: (state: typeof mockConfigState) => unknown) => selector(mockConfigState),
}));

const mockChatState = vi.hoisted(() => ({
  messages: [
    {
      role: 'assistant' as const,
      contextBudget: {
        current_tokens: 5000,
        max_context_tokens: 128000,
        usage_percent: 3.9,
        health_status: 'healthy' as ContextHealthStatus,
      },
    },
  ] as Array<{
    role: 'assistant' | 'user';
    contextBudget?: {
      current_tokens: number;
      max_context_tokens: number;
      usage_percent: number;
      health_status: ContextHealthStatus;
    };
  }>,
  chatId: 'test-chat-123',
  setActiveSessionAnalyticsId: vi.fn(),
}));

vi.mock('@/store/useChatStore', () => ({
  default: (selectorOrShallow: unknown) => {
    if (typeof selectorOrShallow === 'function') {
      return (selectorOrShallow as (state: typeof mockChatState) => unknown)(mockChatState);
    }
    return mockChatState;
  },
}));

vi.mock('zustand/react/shallow', () => ({
  useShallow: (selector: (state: typeof mockChatState) => unknown) => selector,
}));

const mockHealthy: ContextHealth = {
  status: 'healthy',
  compaction: {
    status: 'healthy',
    active: true,
    count: 3,
    tokens_saved: 8200,
    net_tokens_saved: 7800,
    efficiency: 0.85,
    refetch_count: 1,
    refetch_ratio: 0.05,
    dedup_tokens_saved: 400,
    integrity_skipped: 0,
    summary_persisted: true,
    last_compacted_at: '2026-05-28T10:00:00Z',
  },
  pruning: {
    status: 'inactive',
    active: false,
    archived: 0,
    soft_trimmed: 0,
    offload_failed: 0,
    archive_written_count: 0,
    archive_reused_count: 0,
    archive_bytes_written: 0,
    archive_bytes_reused: 0,
    deferred_count: 0,
    deferred_reasons: {},
    archive_deferred_count: 0,
    archive_deferred_reasons: {},
    archive_deferred_soft_trimmed_count: 0,
    archive_deferred_soft_trimmed_reasons: {},
    archive_refetch_count: 0,
    archive_refetch_tokens: 0,
    archive_restore_requested_count: 0,
    archive_restore_allowed_count: 0,
    archive_restore_blocked_count: 0,
    archive_restore_blocked_ratio: 0,
    archive_restore_result_count: 0,
    archive_restore_result_tokens: 0,
    archive_restore_result_lines: 0,
    archive_restore_result_bytes: 0,
    pruning_restore_cost_ratio: 0,
    pruning_restore_roi_ratio: 0,
    archive_restore_block_events: [],
    offload_failure_kinds: {},
    original_tokens: 0,
    tokens_saved: 0,
    net_tokens_saved: 0,
    refetch_ratio: 0,
    backoff_applied: false,
    backoff_reasons: {},
    effective_soft_trim_ratio: 0,
    effective_hard_clear_ratio: 0,
    effective_min_prunable_tokens: 0,
    archive_summary_queued_count: 0,
    archive_summary_succeeded_count: 0,
    archive_summary_failed_count: 0,
    archive_summary_skipped_count: 0,
    archive_summary_skipped_reasons: {},
  },
  cache: {
    status: 'healthy',
    active: true,
    calls: 15,
    input_tokens: 50000,
    cached_tokens: 36000,
    cache_hit_rate: 0.72,
    model_family: 'claude',
    retention_mode: 'observed',
    ttl_seconds: 300,
    policy_reason: 'model_default',
    policy_source_url: '',
    retention_observation_state: 'observed',
    retention_observation_reason: 'sufficient_calls',
    observation_sample_source: 'dominant_model',
    observation_model_name: 'claude-sonnet-4-20250514',
    observed_calls: 15,
    observed_input_tokens: 50000,
    observed_cached_tokens: 36000,
    observed_cache_hit_rate: 0.72,
  },
};

const mockCriticalHealth: ContextHealth = {
  ...mockHealthy,
  status: 'critical',
  pruning: {
    ...mockHealthy.pruning,
    active: true,
    archived: 5,
    archive_restore_blocked_count: 3,
  },
};

const mockAllInactiveHealth: ContextHealth = {
  ...mockHealthy,
  status: 'inactive',
  compaction: { ...mockHealthy.compaction, active: false },
  pruning: { ...mockHealthy.pruning, active: false },
  cache: { ...mockHealthy.cache, active: false },
};

describe('ContextUsageIndicator', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockConfigState.showContextUsage = true;
    mockChatState.messages = [
      {
        role: 'assistant' as const,
        contextBudget: {
          current_tokens: 5000,
          max_context_tokens: 128000,
          usage_percent: 3.9,
          health_status: 'healthy' as const,
        },
      },
    ];
    mockGetSessionAnalytics.mockResolvedValue({ context_health: mockHealthy });
  });

  describe('rendering conditions', () => {
    it('renders the ring indicator when context budget exists', () => {
      render(<ContextUsageIndicator />);
      expect(screen.getByRole('status')).toBeInTheDocument();
    });

    it('does not render when showContextUsage is false', () => {
      mockConfigState.showContextUsage = false;
      const { container } = render(<ContextUsageIndicator />);
      expect(container.firstChild).toBeNull();
    });

    it('does not render when current_tokens is 0', () => {
      mockChatState.messages = [
        {
          role: 'assistant' as const,
          contextBudget: {
            current_tokens: 0,
            max_context_tokens: 128000,
            usage_percent: 0,
            health_status: 'healthy' as const,
          },
        },
      ];
      const { container } = render(<ContextUsageIndicator />);
      expect(container.firstChild).toBeNull();
    });

    it('does not render when no assistant messages with contextBudget', () => {
      mockChatState.messages = [{ role: 'user' as const }] as typeof mockChatState.messages;
      const { container } = render(<ContextUsageIndicator />);
      expect(container.firstChild).toBeNull();
    });
  });

  describe('health status dot', () => {
    it('shows emerald dot for healthy status', () => {
      render(<ContextUsageIndicator />);
      const dot = screen.getByRole('status').querySelector('[aria-hidden="true"]');
      expect(dot).toBeInTheDocument();
      expect(dot?.className).toContain('bg-emerald-500');
    });

    it('shows amber dot for warning status', () => {
      mockChatState.messages = [
        {
          role: 'assistant' as const,
          contextBudget: {
            current_tokens: 96000,
            max_context_tokens: 128000,
            usage_percent: 75,
            health_status: 'warning' as const,
          },
        },
      ];
      render(<ContextUsageIndicator />);
      const dot = screen.getByRole('status').querySelector('[aria-hidden="true"]');
      expect(dot).toBeInTheDocument();
      expect(dot?.className).toContain('bg-amber-500');
    });

    it('shows rose dot for critical status', () => {
      mockChatState.messages = [
        {
          role: 'assistant' as const,
          contextBudget: {
            current_tokens: 120000,
            max_context_tokens: 128000,
            usage_percent: 93.75,
            health_status: 'critical' as const,
          },
        },
      ];
      render(<ContextUsageIndicator />);
      const dot = screen.getByRole('status').querySelector('[aria-hidden="true"]');
      expect(dot).toBeInTheDocument();
      expect(dot?.className).toContain('bg-rose-500');
    });

    it('hides dot when status is inactive (no health_status)', () => {
      mockChatState.messages = [
        {
          role: 'assistant' as const,
          contextBudget: {
            current_tokens: 5000,
            max_context_tokens: 128000,
            usage_percent: 3.9,
            health_status: undefined,
          },
        },
      ] as typeof mockChatState.messages;
      render(<ContextUsageIndicator />);
      const dot = screen.getByRole('status').querySelector('[aria-hidden="true"]');
      expect(dot).toBeNull();
    });
  });

  describe('mini panel', () => {
    it('fetches context health on panel open and shows compaction info', async () => {
      const user = userEvent.setup();
      render(<ContextUsageIndicator />);

      await user.click(screen.getByRole('status'));

      await waitFor(() => {
        expect(mockGetSessionAnalytics).toHaveBeenCalledWith('test-chat-123');
      });

      await waitFor(() => {
        expect(screen.getByText('compaction')).toBeInTheDocument();
      });
    });

    it('shows cache hit rate in mini panel', async () => {
      const user = userEvent.setup();
      render(<ContextUsageIndicator />);

      await user.click(screen.getByRole('status'));

      await waitFor(() => {
        expect(screen.getByText('cache')).toBeInTheDocument();
      });
    });

    it('shows pruning info and restore blocked warning', async () => {
      mockGetSessionAnalytics.mockResolvedValue({ context_health: mockCriticalHealth });
      const user = userEvent.setup();
      render(<ContextUsageIndicator />);

      await user.click(screen.getByRole('status'));

      await waitFor(() => {
        expect(screen.getByText('pruning')).toBeInTheDocument();
      });

      await waitFor(() => {
        expect(screen.getByText(/restoreBlocked/)).toBeInTheDocument();
      });
    });

    it('shows allInactive text when no strategy is active', async () => {
      mockGetSessionAnalytics.mockResolvedValue({ context_health: mockAllInactiveHealth });
      const user = userEvent.setup();
      render(<ContextUsageIndicator />);

      await user.click(screen.getByRole('status'));

      await waitFor(() => {
        expect(screen.getByText('allInactive')).toBeInTheDocument();
      });
    });

    it('handles API failure gracefully showing noData', async () => {
      mockGetSessionAnalytics.mockRejectedValue(new Error('Network error'));
      const user = userEvent.setup();
      render(<ContextUsageIndicator />);

      await user.click(screen.getByRole('status'));

      await waitFor(() => {
        expect(screen.getByText('noData')).toBeInTheDocument();
      });
    });
  });

  describe('deep linking', () => {
    it('calls setActiveSessionAnalyticsId when view details is clicked', async () => {
      const user = userEvent.setup();
      render(<ContextUsageIndicator />);

      await user.click(screen.getByRole('status'));

      await waitFor(() => {
        expect(screen.getByText('viewDetails')).toBeInTheDocument();
      });

      await user.click(screen.getByText('viewDetails'));
      expect(mockChatState.setActiveSessionAnalyticsId).toHaveBeenCalledWith('test-chat-123');
    });
  });

  describe('manual compression', () => {
    it('shows compress button disabled when usage < 30%', async () => {
      const user = userEvent.setup();
      render(<ContextUsageIndicator />);

      await user.click(screen.getByRole('status'));
      await waitFor(() => {
        expect(screen.getByText('compressContext')).toBeInTheDocument();
      });

      const btn = screen.getByText('compressContext').closest('button');
      expect(btn).toBeDisabled();
    });

    it('shows compress button enabled when usage >= 30%', async () => {
      mockChatState.messages = [
        {
          role: 'assistant' as const,
          contextBudget: {
            current_tokens: 50000,
            max_context_tokens: 128000,
            usage_percent: 39,
            health_status: 'healthy' as const,
          },
        },
      ];
      const user = userEvent.setup();
      render(<ContextUsageIndicator />);

      await user.click(screen.getByRole('status'));
      await waitFor(() => {
        const btn = screen.getByText('compressContext').closest('button');
        expect(btn).not.toBeDisabled();
      });
    });

    it('calls compactChat and shows success message on compress', async () => {
      mockChatState.messages = [
        {
          role: 'assistant' as const,
          contextBudget: {
            current_tokens: 50000,
            max_context_tokens: 128000,
            usage_percent: 39,
            health_status: 'healthy' as const,
          },
        },
      ];
      mockCompactChat.mockResolvedValue({ compacted: true, tokens_saved: 15200 });

      const user = userEvent.setup();
      render(<ContextUsageIndicator />);

      await user.click(screen.getByRole('status'));
      await waitFor(() => {
        expect(screen.getByText('compressContext')).toBeInTheDocument();
      });

      await user.click(screen.getByText('compressContext'));

      await waitFor(() => {
        expect(mockCompactChat).toHaveBeenCalledWith('test-chat-123');
      });

      await waitFor(() => {
        expect(screen.getByText(/compressSuccess/)).toBeInTheDocument();
      });
    });

    it('refreshes health data after successful compression', async () => {
      mockChatState.messages = [
        {
          role: 'assistant' as const,
          contextBudget: {
            current_tokens: 50000,
            max_context_tokens: 128000,
            usage_percent: 39,
            health_status: 'healthy' as const,
          },
        },
      ];
      mockCompactChat.mockResolvedValue({ compacted: true, tokens_saved: 10000 });

      const user = userEvent.setup();
      render(<ContextUsageIndicator />);

      await user.click(screen.getByRole('status'));
      await waitFor(() => {
        expect(mockGetSessionAnalytics).toHaveBeenCalledTimes(1);
      });

      mockGetSessionAnalytics.mockClear();
      await user.click(screen.getByText('compressContext'));

      await waitFor(() => {
        expect(mockGetSessionAnalytics).toHaveBeenCalledWith('test-chat-123');
      });
    });

    it('does not refresh health when compression reports not needed', async () => {
      mockChatState.messages = [
        {
          role: 'assistant' as const,
          contextBudget: {
            current_tokens: 50000,
            max_context_tokens: 128000,
            usage_percent: 39,
            health_status: 'healthy' as const,
          },
        },
      ];
      mockCompactChat.mockResolvedValue({ compacted: false, tokens_saved: 0 });

      const user = userEvent.setup();
      render(<ContextUsageIndicator />);

      await user.click(screen.getByRole('status'));
      await waitFor(() => {
        expect(mockGetSessionAnalytics).toHaveBeenCalledTimes(1);
      });

      mockGetSessionAnalytics.mockClear();
      await user.click(screen.getByText('compressContext'));

      await waitFor(() => {
        expect(screen.getByText(/compressNotNeeded/)).toBeInTheDocument();
      });
      expect(mockGetSessionAnalytics).not.toHaveBeenCalled();
    });

    it('shows error message when compression fails', async () => {
      mockChatState.messages = [
        {
          role: 'assistant' as const,
          contextBudget: {
            current_tokens: 50000,
            max_context_tokens: 128000,
            usage_percent: 39,
            health_status: 'healthy' as const,
          },
        },
      ];
      mockCompactChat.mockRejectedValue(new Error('Server error'));

      const user = userEvent.setup();
      render(<ContextUsageIndicator />);

      await user.click(screen.getByRole('status'));
      await waitFor(() => {
        expect(screen.getByText('compressContext')).toBeInTheDocument();
      });

      await user.click(screen.getByText('compressContext'));

      await waitFor(() => {
        expect(screen.getByText('Server error')).toBeInTheDocument();
      });
    });
  });

  describe('usage levels', () => {
    it('uses amber stroke color at 75%+ usage', () => {
      mockChatState.messages = [
        {
          role: 'assistant' as const,
          contextBudget: {
            current_tokens: 96000,
            max_context_tokens: 128000,
            usage_percent: 75,
            health_status: 'warning' as const,
          },
        },
      ];
      render(<ContextUsageIndicator />);
      const circles = screen.getByRole('status').querySelectorAll('circle');
      const progressCircle = circles[1];
      expect(progressCircle?.getAttribute('stroke')).toBe('#f59e0b');
    });

    it('uses red stroke color at 90%+ usage', () => {
      mockChatState.messages = [
        {
          role: 'assistant' as const,
          contextBudget: {
            current_tokens: 120000,
            max_context_tokens: 128000,
            usage_percent: 93.75,
            health_status: 'critical' as const,
          },
        },
      ];
      render(<ContextUsageIndicator />);
      const circles = screen.getByRole('status').querySelectorAll('circle');
      const progressCircle = circles[1];
      expect(progressCircle?.getAttribute('stroke')).toBe('#ef4444');
    });
  });
});
