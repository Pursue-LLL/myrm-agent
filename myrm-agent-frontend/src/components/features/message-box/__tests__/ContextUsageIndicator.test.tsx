import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it } from 'vitest';
import type { ContextBudget } from '@/store/chat/types/contextMetrics';
import { mockChatState, mockConfigState, renderIndicator, resetIndicatorKit } from './contextUsageIndicatorKit';

describe('ContextUsageIndicator', () => {
  beforeEach(resetIndicatorKit);

  describe('rendering conditions', () => {
    it('renders the ring indicator when context budget exists', () => {
      renderIndicator();
      expect(screen.getByRole('status')).toBeInTheDocument();
    });

    it('does not render when showContextUsage is false', () => {
      mockConfigState.showContextUsage = false;
      const { container } = renderIndicator();
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
      const { container } = renderIndicator();
      expect(container.firstChild).toBeNull();
    });

    it('does not render when no assistant messages with contextBudget', () => {
      mockChatState.messages = [{ role: 'user' as const }] as typeof mockChatState.messages;
      const { container } = renderIndicator();
      expect(container.firstChild).toBeNull();
    });
  });

  describe('health status dot', () => {
    it('shows emerald dot for healthy status', () => {
      renderIndicator();
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
      renderIndicator();
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
      renderIndicator();
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
      ] as unknown as typeof mockChatState.messages;
      renderIndicator();
      const dot = screen.getByRole('status').querySelector('[aria-hidden="true"]');
      expect(dot).toBeNull();
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
      renderIndicator();
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
      renderIndicator();
      const circles = screen.getByRole('status').querySelectorAll('circle');
      const progressCircle = circles[1];
      expect(progressCircle?.getAttribute('stroke')).toBe('#ef4444');
    });

    it('shows context breakdown when breakdown fields are present', async () => {
      const user = userEvent.setup();
      mockChatState.messages = [
        {
          role: 'assistant' as const,
          contextBudget: {
            current_tokens: 118000,
            max_context_tokens: 128000,
            usage_percent: 92.2,
            health_status: 'critical' as const,
            messages_estimated_tokens: 112000,
            bound_tools_overhead_tokens: 6000,
            other_tokens: 0,
          },
        },
      ];
      renderIndicator();
      await user.click(screen.getByRole('status'));
      expect(await screen.findByText('breakdownTitle')).toBeInTheDocument();
      expect(screen.getByTestId('context-budget-breakdown')).toBeInTheDocument();
      expect(screen.getByText('breakdownMessages')).toBeInTheDocument();
      expect(screen.getByText('breakdownTools')).toBeInTheDocument();
      expect(screen.getByText('breakdownTotal')).toBeInTheDocument();
    });

    it('shows fine-grained AgentLens 6-category breakdown and health zone badge', async () => {
      const user = userEvent.setup();
      mockChatState.messages = [
        {
          role: 'assistant' as const,
          contextBudget: {
            current_tokens: 45000,
            max_context_tokens: 128000,
            usage_percent: 35.1,
            health_status: 'healthy' as const,
            messages_estimated_tokens: 20000,
            system_prompt_tokens: 5000,
            memory_tokens: 3000,
            workspace_rules_tokens: 2000,
            mcp_tools_tokens: 8000,
            skills_tools_tokens: 4000,
            builtin_tools_tokens: 3000,
          } as ContextBudget,
        },
      ];
      renderIndicator();
      await user.click(screen.getByRole('status'));
      expect(await screen.findByText('breakdownTitle')).toBeInTheDocument();
      expect(screen.getByTestId('context-budget-breakdown')).toBeInTheDocument();
      expect(screen.getByText('breakdownMessages')).toBeInTheDocument();
      expect(screen.getByText('breakdownSystemPrompt')).toBeInTheDocument();
      expect(screen.getByText('breakdownMemory')).toBeInTheDocument();
      expect(screen.getByText('breakdownWorkspaceRules')).toBeInTheDocument();
      expect(screen.getByText('breakdownMcpTools')).toBeInTheDocument();
      expect(screen.getByText('breakdownSkillsTools')).toBeInTheDocument();
      expect(screen.getByText('breakdownBuiltinTools')).toBeInTheDocument();
      expect(screen.getByText('optimalZone')).toBeInTheDocument();
    });
  });
});
