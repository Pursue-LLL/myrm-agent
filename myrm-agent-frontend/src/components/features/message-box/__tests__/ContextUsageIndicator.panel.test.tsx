import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it } from 'vitest';
import {
  mockAllInactiveHealth,
  mockChatState,
  mockCriticalHealth,
  mockGetSessionAnalytics,
  renderIndicator,
  resetIndicatorKit,
} from './contextUsageIndicatorKit';

describe('ContextUsageIndicator panel', () => {
  beforeEach(resetIndicatorKit);

  describe('mini panel', () => {
    it('fetches context health on panel open and shows compaction info', async () => {
      const user = userEvent.setup();
      renderIndicator();

      await user.click(screen.getByRole('status'));

      await waitFor(() => {
        expect(mockGetSessionAnalytics).toHaveBeenCalledWith('test-chat-123', false);
      });

      await waitFor(() => {
        expect(screen.getByText('compaction')).toBeInTheDocument();
      });
    });

    it('shows cache hit rate in mini panel', async () => {
      const user = userEvent.setup();
      renderIndicator();

      await user.click(screen.getByRole('status'));

      await waitFor(() => {
        expect(screen.getByText('cache')).toBeInTheDocument();
      });
    });

    it('shows pruning info and restore blocked warning', async () => {
      mockGetSessionAnalytics.mockResolvedValue({ context_health: mockCriticalHealth });
      const user = userEvent.setup();
      renderIndicator();

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
      renderIndicator();

      await user.click(screen.getByRole('status'));

      await waitFor(() => {
        expect(screen.getByText('allInactive')).toBeInTheDocument();
      });
    });

    it('handles API failure gracefully showing noData', async () => {
      mockGetSessionAnalytics.mockRejectedValue(new Error('Network error'));
      const user = userEvent.setup();
      renderIndicator();

      await user.click(screen.getByRole('status'));

      await waitFor(() => {
        expect(screen.getByText('noData')).toBeInTheDocument();
      });
    });
  });

  describe('deep linking', () => {
    it('calls setActiveSessionAnalyticsId when view details is clicked', async () => {
      const user = userEvent.setup();
      renderIndicator();

      await user.click(screen.getByRole('status'));

      await waitFor(() => {
        expect(screen.getByText('viewDetails')).toBeInTheDocument();
      });

      await user.click(screen.getByText('viewDetails'));
      expect(mockChatState.setActiveSessionAnalyticsId).toHaveBeenCalledWith('test-chat-123');
    });
  });

  describe('fork CTA', () => {
    it('does not show fork button when usage < 75%', async () => {
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
      renderIndicator();

      await user.click(screen.getByRole('status'));
      await waitFor(() => {
        expect(screen.getByText('compressContext')).toBeInTheDocument();
      });

      expect(screen.queryByText('forkNewTopic')).not.toBeInTheDocument();
    });

    it('shows fork button when usage >= 75%', async () => {
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
      const user = userEvent.setup();
      renderIndicator();

      await user.click(screen.getByRole('status'));
      await waitFor(() => {
        expect(screen.getByText('forkNewTopic')).toBeInTheDocument();
      });

      const btn = screen.getByText('forkNewTopic').closest('button');
      expect(btn).not.toBeDisabled();
    });

    it('shows fork button when usage >= 90% (critical)', async () => {
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
      const user = userEvent.setup();
      renderIndicator();

      await user.click(screen.getByRole('status'));
      await waitFor(() => {
        expect(screen.getByText('forkNewTopic')).toBeInTheDocument();
      });
    });
  });
});
